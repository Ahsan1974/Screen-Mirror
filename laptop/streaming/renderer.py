"""Turn one JPEG payload into a QImage. PySide6 decodes JPEG itself."""

from __future__ import annotations

from PySide6.QtGui import QImage


def jpeg_to_qimage(data: bytes) -> QImage | None:
    image = QImage()
    if not image.loadFromData(data, "JPEG"):
        return None
    return image
