"""Discovery parsing, pairing, connection, and reconnect against a local fake phone."""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

import websockets
from websockets.exceptions import ConnectionClosed

from laptop.config.settings import AppConfig
from laptop.network.addresses import is_allowed_host
from laptop.network.discovery import device_from_service_info
from laptop.network.pairing import PairedStore, codes_match, generate_code
from laptop.network.websocket_client import ClientCallbacks, PhoneClient


class FakeInfo:
    def __init__(self, addresses, port=8765, properties=None, name="My Phone._ahsanremote._tcp.local."):
        self._addresses = addresses
        self.port = port
        self.properties = properties or {}
        self.name = name

    def parsed_addresses(self):
        return list(self._addresses)


class FakePhone:
    """Speaks just enough of the phone protocol for the laptop tests."""

    def __init__(self, token: str | None = None, drop_first: bool = False):
        self.token = token
        self.drop_first = drop_first
        self.phone_id = "11111111-1111-1111-1111-111111111111"
        self.phone_name = "Test Phone"
        self.port = 0
        self.messages = []
        self.pair_code = ""
        self.auto_pair = True
        self._server = None
        self._connections = 0

    async def start(self) -> None:
        self._server = await websockets.serve(self._handler, "127.0.0.1", 0, max_size=16 * 1024 * 1024)
        self.port = self._server.sockets[0].getsockname()[1]

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def _handler(self, ws, path=None):
        self._connections += 1
        connection_number = self._connections
        try:
            async for message in ws:
                if isinstance(message, (bytes, bytearray)):
                    self.messages.append(bytes(message))
                    continue
                data = json.loads(message)
                self.messages.append(data)
                kind = data.get("type")
                if kind == "hello":
                    await self._hello(ws, data, connection_number)
                elif kind == "pair_begin" and self.auto_pair:
                    for _ in range(100):
                        if self.pair_code:
                            break
                        await asyncio.sleep(0.02)
                    await ws.send(
                        json.dumps(
                            {
                                "type": "pair_submit",
                                "code": self.pair_code,
                                "phone_id": self.phone_id,
                                "phone_name": self.phone_name,
                            }
                        )
                    )
                elif kind == "pair_ok":
                    self.token = data.get("token")
                elif kind == "ping":
                    await ws.send(json.dumps({"type": "pong", "t": data.get("t")}))
        except ConnectionClosed:
            return

    async def _hello(self, ws, data, connection_number: int) -> None:
        token = data.get("token") or ""
        if self.token and token == self.token:
            await ws.send(
                json.dumps(
                    {
                        "type": "auth_ok",
                        "phone_id": self.phone_id,
                        "phone_name": self.phone_name,
                        "screen_width": 1080,
                        "screen_height": 2400,
                    }
                )
            )
            if self.drop_first and connection_number == 1:
                await ws.close()
            return
        await ws.send(
            json.dumps(
                {
                    "type": "auth_required",
                    "phone_id": self.phone_id,
                    "phone_name": self.phone_name,
                }
            )
        )


class RecordingCallbacks(ClientCallbacks):
    def __init__(self):
        self.errors = []
        self.disconnected = []
        self.pairing_failed = []
        self.codes = []

    def on_protocol_error(self, code: str, message: str) -> None:
        self.errors.append((code, message))

    def on_disconnected(self, message: str, reconnecting: bool) -> None:
        self.disconnected.append((message, reconnecting))

    def on_pairing_failed(self, message: str) -> None:
        self.pairing_failed.append(message)

    def on_pairing_code(self, code: str) -> None:
        self.codes.append(code)


class NetworkTests(unittest.TestCase):
    def test_device_discovery(self):
        device = device_from_service_info(
            FakeInfo(
                ["8.8.8.8", "192.168.1.20"],
                properties={b"name": b"Ahsan Phone", b"id": b"phone-1"},
            )
        )
        self.assertIsNotNone(device)
        self.assertEqual(device.host, "192.168.1.20")
        self.assertEqual(device.port, 8765)
        self.assertEqual(device.name, "Ahsan Phone")
        self.assertEqual(device.phone_id, "phone-1")
        self.assertIsNone(device_from_service_info(FakeInfo(["8.8.8.8"])))
        self.assertTrue(is_allowed_host("10.1.2.3"))
        self.assertTrue(is_allowed_host("172.16.5.5"))
        self.assertTrue(is_allowed_host("192.168.0.8"))
        self.assertFalse(is_allowed_host("172.32.5.5"))
        self.assertTrue(is_allowed_host("127.0.0.1"))
        self.assertFalse(is_allowed_host("example.com"))
        self.assertFalse(is_allowed_host("8.8.8.8"))

    def test_connection(self):
        asyncio.run(self._connection())

    def test_pairing(self):
        asyncio.run(self._pairing())

    def test_reconnection(self):
        asyncio.run(self._reconnection())

    async def _connection(self):
        phone = FakePhone(token="known-token")
        callbacks = RecordingCallbacks()
        with tempfile.TemporaryDirectory() as directory:
            store = PairedStore(Path(directory) / "paired.json")
            store.remember(phone.phone_id, phone.phone_name, "known-token", "127.0.0.1", 1)
            config = AppConfig(reconnect=False, clipboard_auto=False)
            client = PhoneClient(config, store, callbacks, Path(directory))
            await phone.start()
            try:
                await client.start("127.0.0.1", phone.port)
                await client.wait_auth_count(1, timeout=4)
                await client.send_mouse("down", 10, 20, "left")
                await asyncio.sleep(0.1)
                mice = [item for item in phone.messages if isinstance(item, dict) and item.get("type") == "mouse"]
                self.assertTrue(mice)
                self.assertEqual(mice[-1]["x"], 10)
                self.assertEqual(mice[-1]["y"], 20)
            finally:
                await client.close()
                await phone.close()

        rejected = PhoneClient(
            AppConfig(reconnect=False),
            PairedStore(Path(tempfile.mkdtemp()) / "paired.json"),
            callbacks,
            Path(tempfile.mkdtemp()),
        )
        await rejected.start("8.8.8.8", 9)
        await asyncio.wait_for(rejected._task, timeout=2)
        self.assertTrue(any(code == "address" for code, _message in callbacks.errors))

    async def _pairing(self):
        for _ in range(20):
            code = generate_code()
            self.assertEqual(len(code), 6)
            self.assertTrue(code.isdigit())
            self.assertTrue(codes_match(code, code))
            self.assertFalse(codes_match(code, "000000") and code != "000000")

        phone = FakePhone()
        callbacks = RecordingCallbacks()

        class Bridge(RecordingCallbacks):
            def on_pairing_code(self, code: str) -> None:
                super().on_pairing_code(code)
                phone.pair_code = code

        callbacks = Bridge()
        with tempfile.TemporaryDirectory() as directory:
            store = PairedStore(Path(directory) / "paired.json")
            client = PhoneClient(AppConfig(reconnect=False), store, callbacks, Path(directory))
            await phone.start()
            try:
                await client.start("127.0.0.1", phone.port)
                await client.wait_auth_count(1, timeout=4)
                self.assertTrue(store.token_for_host("127.0.0.1"))
                self.assertEqual(len(callbacks.codes), 1)
            finally:
                await client.close()
                await phone.close()

        phone = FakePhone()
        failed = asyncio.Event()

        class Wrong(ClientCallbacks):
            def on_pairing_code(self, code: str) -> None:
                phone.pair_code = "000000"

            def on_pairing_failed(self, message: str) -> None:
                self.message = message
                failed.set()

        wrong = Wrong()
        with tempfile.TemporaryDirectory() as directory:
            client = PhoneClient(
                AppConfig(reconnect=False),
                PairedStore(Path(directory) / "paired.json"),
                wrong,
                Path(directory),
            )
            await phone.start()
            try:
                await client.start("127.0.0.1", phone.port)
                await asyncio.wait_for(failed.wait(), timeout=4)
                self.assertIn("Pairing failed", wrong.message)
                self.assertEqual(client.auth_count, 0)
            finally:
                await client.close()
                await phone.close()

    async def _reconnection(self):
        phone = FakePhone(token="again-token", drop_first=True)
        with tempfile.TemporaryDirectory() as directory:
            store = PairedStore(Path(directory) / "paired.json")
            store.remember(phone.phone_id, phone.phone_name, "again-token", "127.0.0.1", 1)
            config = AppConfig(reconnect=True, reconnect_interval_sec=0.2, clipboard_auto=False)
            client = PhoneClient(config, store, ClientCallbacks(), Path(directory))
            await phone.start()
            try:
                await client.start("127.0.0.1", phone.port)
                await client.wait_auth_count(2, timeout=6)
                self.assertGreaterEqual(client.auth_count, 2)
                self.assertGreaterEqual(phone._connections, 2)
            finally:
                await client.close()
                await phone.close()


if __name__ == "__main__":
    unittest.main()
