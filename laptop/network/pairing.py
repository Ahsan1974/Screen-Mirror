"""Six-digit pairing and the token stored after a phone is trusted.

This is not an account system. The laptop shows a code, you type it on your phone,
and both devices store one random token for next time.
"""

from __future__ import annotations

import hmac
import json
import secrets
import threading
import uuid
from pathlib import Path


def generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def new_token() -> str:
    return secrets.token_urlsafe(32)


def codes_match(expected: str, got: str) -> bool:
    if not expected or len(expected) != len(got):
        return False
    return hmac.compare_digest(expected, got)


class PairedStore:
    """JSON file of phones this laptop has paired with. One phone is the normal case."""

    def __init__(self, path: Path):
        self.path = path
        self.laptop_id = ""
        self.devices: dict[str, dict] = {}
        self._lock = threading.Lock()
        self.load()

    def load(self) -> None:
        with self._lock:
            if not self.path.exists():
                self.laptop_id = str(uuid.uuid4())
                self.devices = {}
                self._write()
                return
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.laptop_id = data.get("laptop_id") or str(uuid.uuid4())
            self.devices = data.get("devices") or {}

    def save(self) -> None:
        with self._lock:
            self._write()

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"laptop_id": self.laptop_id, "devices": self.devices}
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def token_for_host(self, host: str) -> str | None:
        """Return the saved token for this IP, or the only paired phone if the IP changed."""
        with self._lock:
            for device in self.devices.values():
                if device.get("last_ip") == host and device.get("token"):
                    return device["token"]
            if len(self.devices) == 1:
                token = next(iter(self.devices.values())).get("token")
                return token or None
            return None

    def remember(self, phone_id: str, name: str, token: str, host: str, port: int) -> None:
        with self._lock:
            self.devices[phone_id] = {
                "name": name,
                "token": token,
                "last_ip": host,
                "last_port": port,
            }
            self._write()

    def touch(self, phone_id: str, host: str, port: int) -> None:
        with self._lock:
            device = self.devices.get(phone_id)
            if not device:
                return
            device["last_ip"] = host
            device["last_port"] = port
            self._write()

    def forget_all(self) -> None:
        with self._lock:
            self.devices.clear()
            self._write()
