"""Validate a binary screen frame before the UI draws it."""

from __future__ import annotations

from laptop.network.protocol import ProtocolError, VideoFrame, unpack_binary


def decode_frame(data: bytes) -> VideoFrame:
    message = unpack_binary(data)
    if not isinstance(message, VideoFrame):
        raise ProtocolError("binary message is not a screen frame")
    if message.capture_width <= 0 or message.capture_height <= 0:
        raise ProtocolError("frame size is invalid")
    if message.screen_width <= 0 or message.screen_height <= 0:
        raise ProtocolError("screen size is invalid")
    if len(message.jpeg) < 4 or not message.jpeg.startswith(b"\xff\xd8"):
        raise ProtocolError("frame payload is not a JPEG")
    return message
