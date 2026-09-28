"""Protocol messages, pointer mapping, and keyboard translation."""

from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import Qt

from laptop.input.keyboard import translate_key
from laptop.input.mouse import map_pointer, mouse_message
from laptop.network.protocol import FILE_HEADER, FRAME_HEADER, pack_file_chunk, pack_frame, unpack_binary
from laptop.streaming.decoder import decode_frame
from laptop.transfer.file_transfer import file_start_message


class ProtocolTests(unittest.TestCase):
    def test_mouse_message(self):
        message = mouse_message("down", 420, 650, "left")
        self.assertEqual(
            message,
            {"type": "mouse", "action": "down", "x": 420, "y": 650, "button": "left"},
        )
        center = map_pointer(200, 400, 100, 200, 1080, 2400, 100, 200)
        self.assertEqual(center, (540, 1200))
        self.assertIsNone(map_pointer(200, 200, 100, 200, 100, 200, 10, 10))

    def test_keyboard_message(self):
        self.assertEqual(translate_key(Qt.Key_H, "h", 0)["key"], "h")
        self.assertEqual(translate_key(Qt.Key_Return, "", 0)["key"], "ENTER")
        self.assertEqual(translate_key(Qt.Key_Enter, "", 0)["key"], "ENTER")
        self.assertEqual(translate_key(Qt.Key_Backspace, "", 0)["key"], "BACKSPACE")
        self.assertEqual(translate_key(Qt.Key_Delete, "", 0)["key"], "DELETE")
        self.assertEqual(translate_key(Qt.Key_Escape, "", 0)["key"], "ESCAPE")
        self.assertEqual(translate_key(Qt.Key_Left, "", 0)["key"], "LEFT")
        self.assertEqual(translate_key(Qt.Key_Space, "", 0)["key"], "SPACE")
        self.assertEqual(translate_key(Qt.Key_A, "A", Qt.ShiftModifier)["key"], "A")
        self.assertIsNone(translate_key(Qt.Key_C, "c", Qt.ControlModifier))

    def test_file_message(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "photo.jpg"
            path.write_bytes(b"hello")
            file_id = "123e4567-e89b-12d3-a456-426614174000"
            message = file_start_message(path, file_id=file_id)
        self.assertEqual(message["type"], "file_start")
        self.assertEqual(message["name"], "photo.jpg")
        self.assertEqual(message["size"], 5)
        self.assertEqual(len(message["sha256"]), 64)
        chunk = unpack_binary(pack_file_chunk(file_id, 0, True, b"hello"))
        self.assertEqual(chunk.file_id, file_id)
        self.assertEqual(chunk.sequence, 0)
        self.assertTrue(chunk.last)
        self.assertEqual(chunk.payload, b"hello")

    def test_frame_roundtrip(self):
        jpeg = b"\xff\xd8\xff\xd9"
        packed = pack_frame(720, 1280, 1080, 2400, 1234, jpeg)
        self.assertEqual(FRAME_HEADER.size, 25)
        self.assertEqual(FILE_HEADER.size, 42)
        self.assertEqual(struct.calcsize("!BIIIIQ"), 25)
        frame = decode_frame(packed)
        self.assertEqual(frame.capture_width, 720)
        self.assertEqual(frame.capture_height, 1280)
        self.assertEqual(frame.screen_width, 1080)
        self.assertEqual(frame.screen_height, 2400)
        self.assertEqual(frame.timestamp_ms, 1234)
        self.assertEqual(frame.jpeg, jpeg)


if __name__ == "__main__":
    unittest.main()
