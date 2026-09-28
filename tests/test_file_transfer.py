"""Put file chunks back together, including a failed transfer."""

from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path

from laptop.network.protocol import unpack_binary
from laptop.transfer.file_transfer import IncomingFile, TransferError, iter_file_chunks, new_transfer_id


def _assemble(directory: Path, payload: bytes, name: str, sha256: str | None = None) -> IncomingFile:
    file_id = new_transfer_id()
    digest = sha256 if sha256 is not None else hashlib.sha256(payload).hexdigest()
    incoming = IncomingFile(file_id, name, len(payload), digest, directory)
    for blob in iter_file_chunks(file_id, payload):
        incoming.add_chunk(unpack_binary(blob))
    return incoming


class FileTransferTests(unittest.TestCase):
    def test_small_file(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            incoming = _assemble(folder, b"hello world", r"..\photo.jpg")
            self.assertEqual(incoming.final_path.read_bytes(), b"hello world")
            self.assertEqual(incoming.final_path.parent, folder)
            self.assertEqual(incoming.final_path.name, "photo.jpg")
            self.assertFalse(incoming.temp_path.exists())

    def test_large_file(self):
        payload = os.urandom(5 * 1024 * 1024)
        with tempfile.TemporaryDirectory() as directory:
            incoming = _assemble(Path(directory), payload, "clip.bin")
            self.assertEqual(incoming.final_path.read_bytes(), payload)

    def test_transfer_failure(self):
        payload = b"abc123-not-empty"
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            file_id = new_transfer_id()
            incoming = IncomingFile(file_id, "notes.txt", len(payload), "0" * 64, folder)
            with self.assertRaises(TransferError):
                for blob in iter_file_chunks(file_id, payload):
                    incoming.add_chunk(unpack_binary(blob))
            self.assertFalse(incoming.temp_path.exists())
            self.assertFalse(any(folder.glob("notes.txt")))

            ordered = list(iter_file_chunks(new_transfer_id(), b"0123456789" * 8000))
            self.assertGreater(len(ordered), 1)
            other_id = new_transfer_id()
            broken = IncomingFile(
                other_id,
                "broken.bin",
                80000,
                hashlib.sha256(b"0123456789" * 8000).hexdigest(),
                folder,
            )
            # Re-pack is unnecessary: feed the second chunk first by rewriting its id.
            chunk = unpack_binary(ordered[1])
            from laptop.network.protocol import pack_file_chunk

            forged = unpack_binary(pack_file_chunk(other_id, chunk.sequence, chunk.last, chunk.payload))
            with self.assertRaises(TransferError):
                broken.add_chunk(forged)
            self.assertFalse(broken.temp_path.exists())


if __name__ == "__main__":
    unittest.main()
