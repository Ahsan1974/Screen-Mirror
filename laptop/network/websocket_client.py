"""WebSocket session with the phone.

The phone is the server. This laptop connects to it. Pairing works like this:

1. Laptop sends hello, with a saved token when it has one.
2. Phone answers auth_ok, or auth_required when the token is missing.
3. Laptop shows a 6-digit code and sends pair_begin. The code itself is not sent.
4. You type the code on the phone. The phone sends pair_submit.
5. Laptop checks the code, stores a random token, and sends pair_ok.

Screen frames and file chunks are binary. Everything else is a small JSON text message.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import logging
import time
from pathlib import Path

import websockets
from websockets.exceptions import ConnectionClosed

from shared.message_types import (
    AUTH_OK,
    AUTH_REQUIRED,
    CLIPBOARD_DATA,
    CLIPBOARD_MAX_CHARS,
    ERROR,
    FILE_ACCEPT,
    FILE_DONE,
    FILE_ERROR,
    FILE_REJECT,
    FILE_START,
    PAIR_SUBMIT,
    PONG,
    PROTOCOL_VERSION,
    STATUS,
    STREAM_STATE,
)

from laptop.config.settings import AppConfig
from laptop.network.addresses import is_allowed_host
from laptop.network.pairing import PairedStore, codes_match, generate_code, new_token
from laptop.network.protocol import FileChunk, ProtocolError, dumps, loads, pack_file_chunk, unpack_binary
from laptop.streaming.decoder import decode_frame
from laptop.transfer.file_transfer import FILE_CHUNK_SIZE, IncomingFile, TransferError, file_start_message

log = logging.getLogger(__name__)

NO_PHONE_HELP = (
    "No phone found.\n\n"
    "Make sure:\n"
    "✓ Phone Wi-Fi is ON\n"
    "✓ Laptop Wi-Fi is ON\n"
    "✓ Both are connected to the same network\n"
    "✓ Android application is running"
)

PAIRING_FAILED = "Pairing failed.\nPlease try again."
CONNECTION_LOST = "Connection lost.\n\nAttempting to reconnect..."


class ClientCallbacks:
    """Override the methods you care about. The Qt bridge emits signals from these."""

    def on_pairing_code(self, code: str) -> None:
        return None

    def on_pairing_failed(self, message: str) -> None:
        return None

    def on_authed(self, info: dict) -> None:
        return None

    def on_disconnected(self, message: str, reconnecting: bool) -> None:
        return None

    def on_frame(self, frame) -> None:
        return None

    def on_status(self, status: dict) -> None:
        return None

    def on_latency(self, milliseconds: int) -> None:
        return None

    def on_protocol_error(self, code: str, message: str) -> None:
        return None

    def on_file_progress(self, event: dict) -> None:
        return None

    def on_file_offer(self, offer: dict, decision: concurrent.futures.Future) -> None:
        if not decision.done():
            decision.set_result(False)

    def on_clipboard(self, text: str) -> None:
        return None


class PhoneClient:
    def __init__(self, config: AppConfig, store: PairedStore, callbacks: ClientCallbacks, download_dir: Path):
        self.config = config
        self.store = store
        self.callbacks = callbacks
        self.download_dir = download_dir
        self.pairing_code = ""
        self.auth_count = 0
        self.host = ""
        self.port = 0
        self._ws = None
        self._task: asyncio.Task | None = None
        self._user_closed = False
        self._closing = asyncio.Event()
        self._authed = False
        self._expected_code = ""
        self._pair_attempts = 0
        self._send_lock = asyncio.Lock()
        self._file_lock = asyncio.Lock()
        self._ping_task: asyncio.Task | None = None
        self._background: set[asyncio.Task] = set()
        self._accept_waiters: dict[str, asyncio.Future] = {}
        self._done_waiters: dict[str, asyncio.Future] = {}
        self._incoming: dict[str, IncomingFile] = {}
        self._streaming = False

    async def start(self, host: str, port: int) -> None:
        await self.close()
        self._user_closed = False
        self._closing = asyncio.Event()
        self.host = host
        self.port = int(port)
        self._task = asyncio.create_task(self._run(self.host, self.port), name="phone-session")

    async def close(self) -> None:
        self._user_closed = True
        self._closing.set()
        task = self._task
        self._task = None
        if task is not None and task is not asyncio.current_task() and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._authed = False

    async def wait_auth_count(self, count: int, timeout: float = 5) -> None:
        deadline = time.monotonic() + timeout
        while self.auth_count < count:
            if time.monotonic() > deadline:
                raise TimeoutError(f"timed out waiting for auth {count}, have {self.auth_count}")
            await asyncio.sleep(0.02)

    async def send_mouse(self, action: str, x: int, y: int, button: str) -> None:
        if not self._authed:
            return
        await self._send({"type": "mouse", "action": action, "x": int(x), "y": int(y), "button": button})

    async def send_key(self, key: str) -> None:
        if not self._authed:
            return
        await self._send({"type": "key", "key": key})

    async def send_nav(self, action: str) -> None:
        if not self._authed:
            return
        await self._send({"type": "navigation", "action": action})

    async def send_text(self, text: str) -> None:
        if not self._authed:
            return
        await self._send({"type": "text_insert", "text": text[:CLIPBOARD_MAX_CHARS]})

    async def request_screen_text(self) -> None:
        if not self._authed:
            return
        await self._send({"type": "screen_text"})

    async def send_clipboard(self, text: str) -> None:
        if not self._authed:
            return
        await self._send({"type": "clipboard_push", "text": text[:CLIPBOARD_MAX_CHARS]})

    async def pull_clipboard(self) -> None:
        if not self._authed:
            return
        await self._send({"type": "clipboard_pull"})

    async def send_stream_config(self) -> None:
        if not self._authed:
            return
        await self._send(self.config.stream_message())

    async def send_file(self, path: str) -> None:
        if not self._authed or self._ws is None:
            self._progress("", Path(path).name, "send", 0, 0, "error", "Connect to the phone first.")
            return
        async with self._file_lock:
            await self._send_file_locked(Path(path))

    async def _run(self, host: str, port: int) -> None:
        if not is_allowed_host(host):
            self.callbacks.on_protocol_error(
                "address",
                "That address is not on a private network. Use the phone's Wi-Fi IP.",
            )
            self.callbacks.on_disconnected("Disconnected", False)
            return
        ever_linked = False
        while not self._user_closed:
            result = await self._session(host, port)
            if self._user_closed:
                break
            if result == "linked":
                ever_linked = True
            if not self.config.reconnect:
                if result == "refused" and not ever_linked:
                    self.callbacks.on_disconnected(NO_PHONE_HELP, False)
                else:
                    self.callbacks.on_disconnected("Disconnected", False)
                break
            if result == "refused" and not ever_linked:
                self.callbacks.on_disconnected(NO_PHONE_HELP, True)
            else:
                self.callbacks.on_disconnected(CONNECTION_LOST, True)
            try:
                await asyncio.wait_for(self._closing.wait(), self.config.reconnect_interval_sec)
                break
            except asyncio.TimeoutError:
                continue

    async def _session(self, host: str, port: int) -> str:
        uri = f"ws://{host}:{port}"
        try:
            ws = await websockets.connect(
                uri,
                max_size=16 * 1024 * 1024,
                open_timeout=8,
                ping_interval=20,
                ping_timeout=20,
            )
        except (OSError, asyncio.TimeoutError, ConnectionClosed) as exc:
            log.info("No phone found at %s (%s)", uri, exc)
            return "refused"
        self._ws = ws
        self._authed = False
        self._streaming = False
        self._expected_code = ""
        self._pair_attempts = 0
        try:
            hello = {
                "type": "hello",
                "protocol": PROTOCOL_VERSION,
                "laptop_id": self.store.laptop_id,
                "laptop_name": self.config.device_name,
            }
            token = self.store.token_for_host(host)
            if token:
                hello["token"] = token
            await self._send(hello)
            async for message in ws:
                if self._user_closed:
                    break
                if isinstance(message, (bytes, bytearray)):
                    await self._on_binary(bytes(message))
                else:
                    await self._on_text(str(message))
            return "linked"
        except asyncio.CancelledError:
            raise
        except ConnectionClosed:
            log.info("Connection closed")
            return "linked"
        except Exception:
            log.exception("Session error")
            return "linked"
        finally:
            self._authed = False
            await self._stop_ping()
            await self._cancel_background()
            await self._close_socket()
            self._fail_transfers("Connection lost.")

    async def _on_text(self, text: str) -> None:
        try:
            message = loads(text)
        except ProtocolError as exc:
            log.warning("Ignored control message: %s", exc)
            return
        kind = message.get("type")
        if kind == AUTH_REQUIRED:
            await self._begin_pairing(message)
        elif kind == AUTH_OK:
            self._mark_authed(message)
            await self.send_stream_config()
        elif kind == PAIR_SUBMIT:
            await self._on_pair_submit(message)
        elif kind == PONG:
            sent = message.get("t")
            if isinstance(sent, (int, float)):
                elapsed = int(time.monotonic() * 1000) - int(sent)
                if 0 <= elapsed < 60_000:
                    self.callbacks.on_latency(elapsed)
        elif kind == STREAM_STATE:
            streaming = bool(message.get("on"))
            if streaming and not self._streaming:
                log.info("Screen streaming started")
            self._streaming = streaming
            self.callbacks.on_status({"streaming": streaming, **message})
        elif kind == STATUS:
            if message.get("sharing") and not self._streaming:
                log.info("Screen streaming started")
                self._streaming = True
            self.callbacks.on_status(message)
        elif kind == ERROR:
            self.callbacks.on_protocol_error(
                str(message.get("code") or "error"),
                str(message.get("message") or "The phone reported an error."),
            )
        elif kind == FILE_START:
            # Don't block the reader while the save dialog is open.
            self._spawn(self._on_file_start(message))
        elif kind == FILE_ACCEPT:
            self._resolve(self._accept_waiters, str(message.get("id") or ""), True)
        elif kind == FILE_REJECT:
            self._resolve(self._accept_waiters, str(message.get("id") or ""), False)
        elif kind == FILE_DONE:
            file_id = str(message.get("id") or "")
            name = str(message.get("name") or "")
            size = int(message.get("size") or 0)
            self._progress(file_id, name, "send", size, size, "done", "Saved on the phone.")
            self._resolve(self._done_waiters, file_id, True)
        elif kind == FILE_ERROR:
            file_id = str(message.get("id") or "")
            self._progress(
                file_id,
                "",
                "send",
                0,
                0,
                "error",
                str(message.get("message") or "The phone could not save the file."),
            )
            self._resolve(self._done_waiters, file_id, False)
            self._resolve(self._accept_waiters, file_id, False)
        elif kind == CLIPBOARD_DATA:
            self.callbacks.on_clipboard(str(message.get("text") or "")[:CLIPBOARD_MAX_CHARS])
        else:
            log.debug("Ignored message type %s", kind)

    async def _begin_pairing(self, message: dict) -> None:
        if not self._expected_code:
            self.pairing_code = generate_code()
            self._expected_code = self.pairing_code
            self.callbacks.on_pairing_code(self.pairing_code)
        await self._send(
            {
                "type": "pair_begin",
                "laptop_name": self.config.device_name,
                "phone_id": message.get("phone_id", ""),
                "phone_name": message.get("phone_name", ""),
            }
        )

    async def _on_pair_submit(self, message: dict) -> None:
        code = str(message.get("code") or "").strip()
        if not codes_match(self._expected_code, code):
            self._pair_attempts += 1
            await self._send({"type": "pair_fail"})
            self.callbacks.on_pairing_failed(PAIRING_FAILED)
            if self._pair_attempts >= 5:
                log.info("Pairing stopped after 5 wrong codes")
                await self._close_socket()
            return
        phone_id = str(message.get("phone_id") or "")
        phone_name = str(message.get("phone_name") or "Android phone")
        if not phone_id:
            await self._send({"type": "pair_fail"})
            self.callbacks.on_pairing_failed(PAIRING_FAILED)
            return
        token = new_token()
        self.store.remember(phone_id, phone_name, token, self.host, self.port)
        await self._send(
            {
                "type": "pair_ok",
                "token": token,
                "laptop_id": self.store.laptop_id,
                "laptop_name": self.config.device_name,
            }
        )
        self._mark_authed({"phone_id": phone_id, "phone_name": phone_name, "type": AUTH_OK})
        await self.send_stream_config()

    def _mark_authed(self, message: dict) -> None:
        self._authed = True
        self.auth_count += 1
        phone_id = str(message.get("phone_id") or "")
        if phone_id:
            self.store.touch(phone_id, self.host, self.port)
        log.info("Connection established")
        self.callbacks.on_authed(
            {
                "phone_id": phone_id,
                "phone_name": message.get("phone_name") or "Android phone",
                "host": self.host,
                "port": self.port,
            }
        )
        self._start_ping()

    def _start_ping(self) -> None:
        if self._ping_task and not self._ping_task.done():
            return
        self._ping_task = asyncio.create_task(self._ping_loop(), name="phone-ping")

    async def _stop_ping(self) -> None:
        task = self._ping_task
        self._ping_task = None
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _ping_loop(self) -> None:
        while self._authed and not self._user_closed:
            await self._send({"type": "ping", "t": int(time.monotonic() * 1000)})
            try:
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                raise

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def _cancel_background(self) -> None:
        tasks = list(self._background)
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    async def _on_binary(self, data: bytes) -> None:
        try:
            if data[:1] == b"\x01":
                self.callbacks.on_frame(decode_frame(data))
                return
            message = unpack_binary(data)
        except ProtocolError as exc:
            log.warning("Ignored binary message: %s", exc)
            return
        if isinstance(message, FileChunk):
            await self._on_file_chunk(message)

    async def _on_file_start(self, message: dict) -> None:
        file_id = str(message.get("id") or "")
        name = str(message.get("name") or "file")
        try:
            size = int(message.get("size") or 0)
        except (TypeError, ValueError):
            size = -1
        if not file_id or size < 0 or size > 8 * 1024 * 1024 * 1024:
            await self._send({"type": "file_reject", "id": file_id, "reason": "invalid file"})
            return
        offer = {"id": file_id, "name": name, "size": size, "sha256": str(message.get("sha256") or "")}
        decision: concurrent.futures.Future = concurrent.futures.Future()
        self.callbacks.on_file_offer(offer, decision)
        try:
            accepted = await asyncio.wait_for(asyncio.wrap_future(decision), timeout=120)
        except asyncio.TimeoutError:
            accepted = False
        if not accepted:
            await self._send({"type": "file_reject", "id": file_id, "reason": "declined"})
            return
        try:
            incoming = IncomingFile(file_id, name, size, offer["sha256"], self.download_dir)
        except TransferError as exc:
            await self._send({"type": "file_error", "id": file_id, "message": str(exc)})
            return
        self._incoming[file_id] = incoming
        log.info("File transfer started: %s", name)
        self._progress(file_id, name, "receive", 0, size, "transferring", "")
        await self._send({"type": "file_accept", "id": file_id})

    async def _on_file_chunk(self, chunk: FileChunk) -> None:
        incoming = self._incoming.get(chunk.file_id)
        if incoming is None:
            return
        try:
            finished = incoming.add_chunk(chunk)
        except TransferError as exc:
            self._incoming.pop(chunk.file_id, None)
            self._progress(chunk.file_id, incoming.name, "receive", incoming.received, incoming.size, "error", str(exc))
            await self._send({"type": "file_error", "id": chunk.file_id, "message": str(exc)})
            return
        if not finished:
            self._progress(
                chunk.file_id,
                incoming.name,
                "receive",
                incoming.received,
                incoming.size,
                "transferring",
                "",
            )
            return
        self._incoming.pop(chunk.file_id, None)
        saved = str(incoming.final_path or "")
        self._progress(chunk.file_id, incoming.name, "receive", incoming.size, incoming.size, "done", saved)
        await self._send(
            {"type": "file_done", "id": incoming.file_id, "name": incoming.name, "size": incoming.size}
        )

    async def _send_file_locked(self, path: Path) -> None:
        if not path.is_file():
            self._progress("", path.name, "send", 0, 0, "error", "Choose a file, not a folder.")
            return
        offer = file_start_message(path)
        file_id = offer["id"]
        size = int(offer["size"])
        loop = asyncio.get_running_loop()
        accept_waiter: asyncio.Future = loop.create_future()
        done_waiter: asyncio.Future = loop.create_future()
        self._accept_waiters[file_id] = accept_waiter
        self._done_waiters[file_id] = done_waiter
        log.info("File transfer started: %s", path.name)
        self._progress(file_id, path.name, "send", 0, size, "offered", "Waiting for the phone…")
        try:
            await self._send(offer)
            try:
                accepted = await asyncio.wait_for(accept_waiter, timeout=120)
            except asyncio.TimeoutError:
                self._progress(file_id, path.name, "send", 0, size, "error", "The phone did not answer.")
                return
            if not accepted:
                self._progress(file_id, path.name, "send", 0, size, "error", "The phone declined the file.")
                return
            sent = 0
            sequence = 0
            with path.open("rb") as handle:
                while True:
                    piece = handle.read(FILE_CHUNK_SIZE)
                    if piece == b"" and sent > 0:
                        break
                    last = sent + len(piece) >= size
                    await self._send_bytes(pack_file_chunk(file_id, sequence, last, piece))
                    sent += len(piece)
                    sequence += 1
                    self._progress(file_id, path.name, "send", sent, size, "transferring", "")
                    if last:
                        break
            try:
                finished = await asyncio.wait_for(done_waiter, timeout=60)
            except asyncio.TimeoutError:
                self._progress(file_id, path.name, "send", sent, size, "error", "The phone did not confirm the file.")
                return
            if not finished:
                return
        finally:
            self._accept_waiters.pop(file_id, None)
            self._done_waiters.pop(file_id, None)

    def _resolve(self, waiters: dict[str, asyncio.Future], file_id: str, value: bool) -> None:
        waiter = waiters.get(file_id)
        if waiter is not None and not waiter.done():
            waiter.set_result(value)

    def _progress(
        self,
        file_id: str,
        name: str,
        direction: str,
        done: int,
        size: int,
        state: str,
        message: str,
    ) -> None:
        self.callbacks.on_file_progress(
            {
                "id": file_id,
                "name": name,
                "direction": direction,
                "bytes": done,
                "size": size,
                "state": state,
                "message": message,
            }
        )

    def _fail_transfers(self, message: str) -> None:
        for incoming in list(self._incoming.values()):
            incoming.abort()
            self._progress(incoming.file_id, incoming.name, "receive", incoming.received, incoming.size, "error", message)
        self._incoming.clear()
        for waiters in (self._accept_waiters, self._done_waiters):
            for waiter in waiters.values():
                if not waiter.done():
                    waiter.set_result(False)

    async def _send(self, message: dict) -> None:
        ws = self._ws
        if ws is None:
            return
        async with self._send_lock:
            try:
                await ws.send(dumps(message))
            except ConnectionClosed:
                log.info("Could not send %s because the socket closed", message.get("type"))

    async def _send_bytes(self, data: bytes) -> None:
        ws = self._ws
        if ws is None:
            return
        async with self._send_lock:
            try:
                await ws.send(data)
            except ConnectionClosed:
                log.info("Could not send binary data because the socket closed")

    async def _close_socket(self) -> None:
        ws = self._ws
        self._ws = None
        if ws is None:
            return
        with contextlib.suppress(Exception):
            await ws.close()
