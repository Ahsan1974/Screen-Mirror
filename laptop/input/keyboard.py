"""Translate laptop keys into the small set the phone knows how to apply.

Ctrl, Alt, and the Windows key are not forwarded. Ctrl+C still copies on the
laptop, and clipboard sync can carry that text to the phone.
Escape is forwarded as ESCAPE. Android does not let a normal app inject
KEYCODE_ESCAPE, so the phone performs Back. That limitation is documented
in docs/android_permissions.md.
"""

from __future__ import annotations

from PySide6.QtCore import Qt


def _as_int(value) -> int:
    """PySide6 6.11 flag values are not accepted by int() directly."""
    raw = getattr(value, "value", value)
    return int(raw)


def translate_key(key: int, text: str, modifiers: int) -> dict | None:
    key = _as_int(key)
    modifiers = _as_int(modifiers)
    blocked = _as_int(Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier)
    if modifiers & blocked:
        return None
    special = {
        _as_int(Qt.Key_Return): "ENTER",
        _as_int(Qt.Key_Enter): "ENTER",
        _as_int(Qt.Key_Backspace): "BACKSPACE",
        _as_int(Qt.Key_Delete): "DELETE",
        _as_int(Qt.Key_Escape): "ESCAPE",
        _as_int(Qt.Key_Left): "LEFT",
        _as_int(Qt.Key_Right): "RIGHT",
        _as_int(Qt.Key_Up): "UP",
        _as_int(Qt.Key_Down): "DOWN",
        _as_int(Qt.Key_Space): "SPACE",
    }
    if key in special:
        return {"type": "key", "key": special[key]}
    if text and text.isprintable() and len(text) == 1:
        return {"type": "key", "key": text}
    return None
