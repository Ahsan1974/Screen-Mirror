"""Find phones advertising _ahsanremote._tcp.local. on the LAN.

mDNS uses multicast UDP on the local network. It does not use the internet.
If a router isolates Wi-Fi clients, discovery stays empty and manual IP still works.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

from zeroconf import ServiceBrowser, ServiceListener, Zeroconf

from laptop.network.addresses import choose_host

SERVICE_TYPE = "_ahsanremote._tcp.local."
log = logging.getLogger(__name__)


@dataclass(frozen=True)
class DiscoveredDevice:
    name: str
    host: str
    port: int
    phone_id: str = ""


def _property(properties: dict | None, key: str) -> str:
    if not properties:
        return ""
    raw = properties.get(key.encode())
    if raw is None:
        raw = properties.get(key)
    if raw is None:
        return ""
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return str(raw)


def instance_name(service_name: str, service_type: str = SERVICE_TYPE) -> str:
    if service_name.endswith(service_type):
        return service_name[: -len(service_type)].rstrip(".")
    return service_name.split(".")[0] or service_name


def device_from_service_info(info, fallback_name: str = "") -> DiscoveredDevice | None:
    """Turn one mDNS record into a device, or None if its address is not on the LAN."""
    if info is None:
        return None
    try:
        addresses = list(info.parsed_addresses())
        port = int(info.port)
    except (AttributeError, TypeError, ValueError):
        return None
    host = choose_host(addresses)
    if host is None or port <= 0:
        return None
    properties = getattr(info, "properties", {}) or {}
    name = _property(properties, "name") or fallback_name or instance_name(getattr(info, "name", ""))
    phone_id = _property(properties, "id")
    return DiscoveredDevice(name=name or "Android phone", host=host, port=port, phone_id=phone_id)


class Discovery:
    def __init__(self):
        self._callbacks: list = []
        self._devices: dict[str, DiscoveredDevice] = {}
        self._lock = threading.Lock()
        self._zeroconf: Zeroconf | None = None
        self._browser: ServiceBrowser | None = None
        self._listener = _Listener(self)

    def add_listener(self, callback) -> None:
        self._callbacks.append(callback)

    def devices(self) -> list[DiscoveredDevice]:
        with self._lock:
            return list(self._devices.values())

    def start(self) -> None:
        if self._zeroconf is not None:
            return
        self._zeroconf = Zeroconf()
        self._browser = ServiceBrowser(self._zeroconf, SERVICE_TYPE, self._listener)
        log.info("Searching for phones")

    def stop(self) -> None:
        if self._browser is not None:
            self._browser.cancel()
            self._browser = None
        if self._zeroconf is not None:
            self._zeroconf.close()
            self._zeroconf = None

    def _replace(self, service_name: str, device: DiscoveredDevice | None) -> None:
        with self._lock:
            if device is None:
                removed = self._devices.pop(service_name, None)
                if removed is None:
                    return
            else:
                previous = self._devices.get(service_name)
                self._devices[service_name] = device
                if previous != device:
                    log.info("Device discovered: %s at %s:%s", device.name, device.host, device.port)
            snapshot = list(self._devices.values())
        for callback in self._callbacks:
            callback(snapshot)


class _Listener(ServiceListener):
    def __init__(self, discovery: Discovery):
        self._discovery = discovery

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        self._update(zc, type_, name)

    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        self._update(zc, type_, name)

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        self._discovery._replace(name, None)

    def _update(self, zc: Zeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name, timeout=3000)
        device = device_from_service_info(info, fallback_name=instance_name(name))
        self._discovery._replace(name, device)
