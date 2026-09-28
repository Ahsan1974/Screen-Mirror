"""Load and save config.yaml. Defaults keep the app usable if the file is missing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = ROOT / "config.yaml"

QUALITY_TO_JPEG = {"low": 40, "medium": 60, "high": 80}


@dataclass
class AppConfig:
    device_name: str = "My PC"
    port: int = 8765
    max_width: int = 1280
    max_height: int = 1280
    fps: int = 15
    jpeg_quality: int = 60
    quality_label: str = "medium"
    reconnect: bool = True
    reconnect_interval_sec: float = 2.0
    clipboard_auto: bool = True
    path: Path = DEFAULT_CONFIG_PATH

    def stream_message(self) -> dict:
        return {
            "type": "stream_start",
            "max_width": self.max_width,
            "max_height": self.max_height,
            "fps": self.fps,
            "quality": self.jpeg_quality,
        }


def _clamp_int(value, default: int, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def _quality(value) -> tuple[int, str]:
    if isinstance(value, str):
        label = value.strip().lower()
        if label in QUALITY_TO_JPEG:
            return QUALITY_TO_JPEG[label], label
        if label.isdigit():
            jpeg = _clamp_int(label, 60, 30, 90)
            return jpeg, str(jpeg)
        return 60, "medium"
    jpeg = _clamp_int(value, 60, 30, 90)
    for label, number in QUALITY_TO_JPEG.items():
        if number == jpeg:
            return jpeg, label
    return jpeg, str(jpeg)


def load_config(path: Path | None = None) -> AppConfig:
    config_path = path or DEFAULT_CONFIG_PATH
    raw: dict = {}
    if config_path.exists():
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            raw = loaded
    network = raw.get("network") or {}
    stream = raw.get("stream") or {}
    connection = raw.get("connection") or {}
    clipboard = raw.get("clipboard") or {}
    jpeg, label = _quality(stream.get("quality", "medium"))
    name = str(raw.get("device_name") or "My PC").strip() or "My PC"
    interval = connection.get("reconnect_interval_sec", 2)
    try:
        interval_sec = float(interval)
    except (TypeError, ValueError):
        interval_sec = 2.0
    return AppConfig(
        device_name=name[:40],
        port=_clamp_int(network.get("port", 8765), 8765, 1024, 65535),
        max_width=_clamp_int(stream.get("width", stream.get("max_width", 1280)), 1280, 240, 1920),
        max_height=_clamp_int(stream.get("height", stream.get("max_height", 1280)), 1280, 240, 1920),
        fps=_clamp_int(stream.get("fps", 15), 15, 5, 30),
        jpeg_quality=jpeg,
        quality_label=label,
        reconnect=bool(connection.get("reconnect", True)),
        reconnect_interval_sec=max(0.2, min(30.0, interval_sec)),
        clipboard_auto=bool(clipboard.get("auto_sync", True)),
        path=config_path,
    )


def save_config(config: AppConfig) -> None:
    payload = {
        "device_name": config.device_name,
        "network": {"port": config.port},
        "stream": {
            "width": config.max_width,
            "height": config.max_height,
            "fps": config.fps,
            "quality": config.quality_label,
        },
        "connection": {
            "reconnect": config.reconnect,
            "reconnect_interval_sec": config.reconnect_interval_sec,
        },
        "clipboard": {"auto_sync": config.clipboard_auto},
    }
    config.path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
