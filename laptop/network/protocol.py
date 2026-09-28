"""JSON control messages and the binary header for frames and file chunks.

Binary layout, big-endian:

JPEG frame (25 byte header + JPEG bytes):
    uint8  type = 1
    uint32 capture width
    uint32 capture height
    uint32 screen width
    uint32 screen height
    uint64 timestamp milliseconds
    JPEG bytes

File chunk (42 byte header + payload):
    uint8  type = 2
    36 byte ASCII UUID
    uint32 sequence starting at 0
    uint8  flags (bit 0 = last chunk)
    payload bytes

The Android class Protocol.kt writes the same bytes. Tests round-trip them.
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass

from shared.message_types import BINARY_FILE_CHUNK, BINARY_FRAME

FRAME_HEADER = struct.Struct("!BIIIIQ")
FILE_HEADER = struct.Struct("!B36sIB")


class ProtocolError(ValueError):
    """A message did not match the protocol."""


@dataclass
class VideoFrame:
    capture_width: int
    capture_height: int
    screen_width: int
    screen_height: int
    timestamp_ms: int
    jpeg: bytes


@dataclass
class FileChunk:
    file_id: str
    sequence: int
    last: bool
    payload: bytes


def dumps(message: dict) -> str:
    return json.dumps(message, separators=(",", ":"))


def loads(text: str) -> dict:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProtocolError("control message is not JSON") from exc
    if not isinstance(data, dict) or "type" not in data:
        raise ProtocolError("control message needs a type")
    return data


def pack_frame(
    capture_width: int,
    capture_height: int,
    screen_width: int,
    screen_height: int,
    timestamp_ms: int,
    jpeg: bytes,
) -> bytes:
    header = FRAME_HEADER.pack(
        BINARY_FRAME,
        int(capture_width),
        int(capture_height),
        int(screen_width),
        int(screen_height),
        int(timestamp_ms),
    )
    return header + jpeg


def pack_file_chunk(file_id: str, sequence: int, last: bool, payload: bytes) -> bytes:
    identity = file_id.encode("ascii")
    if len(identity) != 36:
        raise ProtocolError("file id must be a 36-character UUID")
    header = FILE_HEADER.pack(BINARY_FILE_CHUNK, identity, int(sequence), 1 if last else 0)
    return header + payload


def unpack_binary(data: bytes) -> VideoFrame | FileChunk:
    if not data:
        raise ProtocolError("empty binary message")
    kind = data[0]
    if kind == BINARY_FRAME:
        if len(data) < FRAME_HEADER.size:
            raise ProtocolError("JPEG frame header is short")
        _, cap_w, cap_h, scr_w, scr_h, timestamp = FRAME_HEADER.unpack_from(data)
        return VideoFrame(cap_w, cap_h, scr_w, scr_h, timestamp, data[FRAME_HEADER.size :])
    if kind == BINARY_FILE_CHUNK:
        if len(data) < FILE_HEADER.size:
            raise ProtocolError("file chunk header is short")
        _, identity, sequence, flags = FILE_HEADER.unpack_from(data)
        return FileChunk(
            file_id=identity.decode("ascii"),
            sequence=sequence,
            last=bool(flags & 1),
            payload=data[FILE_HEADER.size :],
        )
    raise ProtocolError(f"unknown binary type {kind}")
