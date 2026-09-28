"""Chunk files and put the chunks back together on disk.

Chunks are binary WebSocket messages, not JSON. See laptop/network/protocol.py.
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from shared.message_types import FILE_CHUNK_SIZE

from laptop.network.protocol import FileChunk, pack_file_chunk


class TransferError(Exception):
    """The file could not be assembled."""


def new_transfer_id() -> str:
    return str(uuid.uuid4())


def safe_name(name: str) -> str:
    base = Path(name).name.replace("\x00", "").strip()
    if base in {"", ".", ".."}:
        return "file"
    return base[:180]


def unique_path(directory: Path, name: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    candidate = directory / safe_name(name)
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    for number in range(2, 1000):
        alternate = directory / f"{stem} ({number}){suffix}"
        if not alternate.exists():
            return alternate
    return directory / f"{stem}-{new_transfer_id()}{suffix}"


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(FILE_CHUNK_SIZE), b""):
            digest.update(block)
    return digest.hexdigest()


def file_start_message(path: Path, file_id: str | None = None) -> dict:
    identity = file_id or new_transfer_id()
    return {
        "type": "file_start",
        "id": identity,
        "name": path.name,
        "size": path.stat().st_size,
        "sha256": hash_file(path),
    }


def iter_file_chunks(file_id: str, payload: bytes, chunk_size: int = FILE_CHUNK_SIZE):
    if not payload:
        yield pack_file_chunk(file_id, 0, True, b"")
        return
    sequence = 0
    for offset in range(0, len(payload), chunk_size):
        piece = payload[offset : offset + chunk_size]
        last = offset + chunk_size >= len(payload)
        yield pack_file_chunk(file_id, sequence, last, piece)
        sequence += 1


class IncomingFile:
    """Write chunks in order and publish the file only after the checksum matches."""

    def __init__(self, file_id: str, name: str, size: int, sha256: str, directory: Path):
        if size < 0:
            raise TransferError("file size is invalid")
        self.file_id = file_id
        self.name = safe_name(name)
        self.size = int(size)
        self.sha256 = (sha256 or "").lower()
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.temp_path = self.directory / f".{file_id}.partial"
        self.received = 0
        self._next_seq = 0
        self._hasher = hashlib.sha256()
        self._handle = self.temp_path.open("wb")
        self.final_path: Path | None = None

    def add_chunk(self, chunk: FileChunk) -> bool:
        if chunk.file_id != self.file_id:
            raise TransferError("chunk belongs to another file")
        if chunk.sequence != self._next_seq:
            self.abort()
            raise TransferError("file chunk arrived out of order")
        self._handle.write(chunk.payload)
        self._hasher.update(chunk.payload)
        self.received += len(chunk.payload)
        self._next_seq += 1
        if not chunk.last:
            return False
        self._handle.close()
        if self.received != self.size:
            self.abort()
            raise TransferError("file size did not match")
        actual = self._hasher.hexdigest()
        if self.sha256 and actual != self.sha256:
            self.abort()
            raise TransferError("file checksum did not match")
        self.final_path = unique_path(self.directory, self.name)
        self.temp_path.replace(self.final_path)
        return True

    def abort(self) -> None:
        try:
            self._handle.close()
        except OSError:
            pass
        self.temp_path.unlink(missing_ok=True)
