"""Run the asyncio client beside Qt, and browse the LAN for phones."""

from __future__ import annotations

import asyncio
import logging
import threading

from PySide6.QtCore import QObject, QThread, Signal

from laptop.config.settings import AppConfig
from laptop.network.discovery import Discovery
from laptop.network.pairing import PairedStore
from laptop.network.websocket_client import ClientCallbacks, PhoneClient

log = logging.getLogger(__name__)


def _consume_future(future) -> None:
    try:
        future.result()
    except asyncio.CancelledError:
        pass
    except Exception:
        log.exception("Network task failed")


class LoopThread(QThread):
    """One asyncio loop for the socket, so the window stays on the Qt thread."""

    def __init__(self):
        super().__init__()
        self.loop: asyncio.AbstractEventLoop | None = None
        self.ready = threading.Event()

    def run(self) -> None:
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.ready.set()
        self.loop.run_forever()
        pending = asyncio.all_tasks(self.loop)
        for task in pending:
            task.cancel()
        if pending:
            self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        self.loop.close()

    def submit(self, coro):
        if not self.ready.wait(5) or self.loop is None:
            coro.close()
            raise RuntimeError("The network loop is not running.")
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        future.add_done_callback(_consume_future)
        return future

    def stop(self) -> None:
        if self.loop is not None:
            self.loop.call_soon_threadsafe(self.loop.stop)
        self.wait(4000)


class _Bridge(ClientCallbacks):
    def __init__(self, controller: "NetworkController"):
        self.controller = controller

    def on_pairing_code(self, code: str) -> None:
        self.controller.pairing_required.emit(code)

    def on_pairing_failed(self, message: str) -> None:
        self.controller.pairing_failed.emit(message)

    def on_authed(self, info: dict) -> None:
        self.controller.authed.emit(info)

    def on_disconnected(self, message: str, reconnecting: bool) -> None:
        self.controller.disconnected.emit(message, reconnecting)

    def on_frame(self, frame) -> None:
        self.controller.frame_received.emit(frame)

    def on_status(self, status: dict) -> None:
        self.controller.status_received.emit(status)

    def on_latency(self, milliseconds: int) -> None:
        self.controller.latency_received.emit(milliseconds)

    def on_protocol_error(self, code: str, message: str) -> None:
        self.controller.protocol_error.emit(code, message)

    def on_file_progress(self, event: dict) -> None:
        self.controller.file_progress.emit(event)

    def on_file_offer(self, offer: dict, decision) -> None:
        self.controller.file_offer.emit(offer, decision)

    def on_clipboard(self, text: str) -> None:
        self.controller.clipboard_received.emit(text)


class NetworkController(QObject):
    devices_changed = Signal(list)
    pairing_required = Signal(str)
    pairing_failed = Signal(str)
    authed = Signal(dict)
    disconnected = Signal(str, bool)
    frame_received = Signal(object)
    status_received = Signal(dict)
    latency_received = Signal(int)
    protocol_error = Signal(str, str)
    file_progress = Signal(dict)
    file_offer = Signal(object, object)
    clipboard_received = Signal(str)

    def __init__(self, config: AppConfig, store: PairedStore, download_dir, parent=None):
        super().__init__(parent)
        self.config = config
        self.store = store
        self.loop_thread = LoopThread()
        self.client = PhoneClient(config, store, _Bridge(self), download_dir)
        self.discovery = Discovery()
        self.discovery.add_listener(self.devices_changed.emit)

    def start(self) -> None:
        self.loop_thread.start()
        self.discovery.start()

    def shutdown(self) -> None:
        self.discovery.stop()
        if self.loop_thread.loop is not None:
            future = asyncio.run_coroutine_threadsafe(self.client.close(), self.loop_thread.loop)
            try:
                future.result(timeout=3)
            except Exception:
                log.exception("Could not close the phone session cleanly")
        self.loop_thread.stop()

    def connect_to(self, host: str, port: int) -> None:
        self.loop_thread.submit(self.client.start(host, port))

    def disconnect_phone(self) -> None:
        self.loop_thread.submit(self.client.close())

    def send_mouse(self, action: str, x: int, y: int, button: str) -> None:
        self.loop_thread.submit(self.client.send_mouse(action, x, y, button))

    def send_key(self, key: str) -> None:
        self.loop_thread.submit(self.client.send_key(key))

    def send_nav(self, action: str) -> None:
        self.loop_thread.submit(self.client.send_nav(action))

    def send_file(self, path: str) -> None:
        self.loop_thread.submit(self.client.send_file(path))

    def send_clipboard(self, text: str) -> None:
        self.loop_thread.submit(self.client.send_clipboard(text))

    def pull_clipboard(self) -> None:
        self.loop_thread.submit(self.client.pull_clipboard())

    def send_stream_config(self) -> None:
        self.loop_thread.submit(self.client.send_stream_config())
