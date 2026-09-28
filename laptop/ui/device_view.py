"""The live phone screen and the buttons around it."""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from laptop.input.keyboard import translate_key
from laptop.input.mouse import letterbox, map_pointer
from laptop.network.protocol import VideoFrame


class ScreenWidget(QWidget):
    """Draws the latest JPEG and turns the pointer into phone coordinates."""

    pointer = Signal(str, int, int, str)
    key_typed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(280, 480)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(False)
        self.image = QImage()
        self.capture_w = 0
        self.capture_h = 0
        self.screen_w = 0
        self.screen_h = 0
        self._button = "left"
        self._last_move = 0.0

    def set_frame(self, image: QImage, frame: VideoFrame) -> None:
        self.image = image
        self.capture_w = frame.capture_width
        self.capture_h = frame.capture_height
        self.screen_w = frame.screen_width
        self.screen_h = frame.screen_height
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#111417"))
        if self.image.isNull() or self.capture_w <= 0:
            painter.setPen(QColor("#d6d3d1"))
            painter.drawText(self.rect(), Qt.AlignCenter, "Start screen sharing on the phone")
            return
        box = letterbox(self.width(), self.height(), self.capture_w, self.capture_h)
        if box is None:
            return
        off_x, off_y, draw_w, draw_h, _scale = box
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.drawImage(int(off_x), int(off_y), self.image.scaled(
            int(draw_w),
            int(draw_h),
            Qt.IgnoreAspectRatio,
            Qt.SmoothTransformation,
        ))

    def mousePressEvent(self, event) -> None:
        self.setFocus()
        if event.button() == Qt.RightButton:
            self._button = "right"
        elif event.button() == Qt.LeftButton:
            self._button = "left"
        else:
            event.ignore()
            return
        # Accept the press so Qt keeps sending move and release to this widget.
        self.grabMouse()
        self._emit_pointer("down", event.position().x(), event.position().y())
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._button == "right":
            event.accept()
            return
        if not (event.buttons() & Qt.LeftButton):
            event.ignore()
            return
        now = time.monotonic()
        if now - self._last_move < 0.03:
            event.accept()
            return
        self._last_move = now
        self._emit_pointer("move", event.position().x(), event.position().y())
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if self.mouseGrabber() is self:
            self.releaseMouse()
        button = "right" if event.button() == Qt.RightButton else "left"
        self._emit_pointer("up", event.position().x(), event.position().y(), button)
        self._button = "left"
        event.accept()

    def keyPressEvent(self, event) -> None:
        message = translate_key(event.key(), event.text(), event.modifiers())
        if message is None:
            super().keyPressEvent(event)
            return
        self.key_typed.emit(message["key"])
        event.accept()

    def _emit_pointer(self, action: str, x: float, y: float, button: str | None = None) -> None:
        mapped = map_pointer(
            self.width(),
            self.height(),
            self.capture_w,
            self.capture_h,
            self.screen_w,
            self.screen_h,
            x,
            y,
        )
        if mapped is None:
            return
        self.pointer.emit(action, mapped[0], mapped[1], button or self._button)


class DeviceView(QWidget):
    pointer = Signal(str, int, int, str)
    key_typed = Signal(str)
    nav_requested = Signal(str)
    file_requested = Signal()
    files_dropped = Signal(list)
    clipboard_requested = Signal()
    settings_requested = Signal()
    disconnect_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.device = QLabel("Device: —")
        self.device.setObjectName("cardTitle")
        self.dot = QLabel("● Disconnected")
        self.dot.setObjectName("bad")
        self.address = QLabel("IP: —")
        self.stream = QLabel("Screen streaming: OFF")
        self.banner = QLabel("")
        self.banner.setObjectName("banner")
        self.banner.setWordWrap(True)
        self.banner.setVisible(False)
        self.screen = ScreenWidget()
        self.screen.pointer.connect(self.pointer.emit)
        self.screen.key_typed.connect(self.key_typed.emit)
        bezel = QFrame()
        bezel.setObjectName("bezel")
        bezel_layout = QVBoxLayout(bezel)
        bezel_layout.setContentsMargins(14, 14, 14, 14)
        bezel_layout.addWidget(self.screen)
        disconnect = QPushButton("Disconnect")
        disconnect.clicked.connect(self.disconnect_requested.emit)
        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.addWidget(self.device)
        titles.addWidget(self.address)
        titles.addWidget(self.stream)
        header.addLayout(titles, 1)
        header.addWidget(self.dot, alignment=Qt.AlignTop)
        header.addWidget(disconnect, alignment=Qt.AlignTop)
        nav = QHBoxLayout()
        for label, action in (("← Back", "BACK"), ("Home", "HOME"), ("Recents", "RECENTS")):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, name=action: self.nav_requested.emit(name))
            nav.addWidget(button)
        nav.addStretch(1)
        hint = QLabel("Click the screen, then type. Right-click is a long press. Ctrl+C stays on the laptop.")
        hint.setObjectName("subhead")
        hint.setWordWrap(True)
        actions = QHBoxLayout()
        transfer = QPushButton("Transfer file")
        transfer.setObjectName("primary")
        transfer.clicked.connect(self.file_requested.emit)
        clipboard = QPushButton("Clipboard")
        clipboard.clicked.connect(self.clipboard_requested.emit)
        settings = QPushButton("Settings")
        settings.clicked.connect(self.settings_requested.emit)
        actions.addWidget(transfer)
        actions.addWidget(clipboard)
        actions.addWidget(settings)
        actions.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 12)
        layout.setSpacing(10)
        layout.addLayout(header)
        layout.addWidget(self.banner)
        layout.addWidget(bezel, 1)
        layout.addLayout(nav)
        layout.addWidget(hint)
        layout.addLayout(actions)

    def set_connection(self, name: str, host: str, connected: bool, reconnecting: bool) -> None:
        self.device.setText(f"Device: {name}")
        self.address.setText(f"IP: {host}")
        if connected:
            self.dot.setText("● Connected")
            self.dot.setObjectName("good")
        elif reconnecting:
            self.dot.setText("● Reconnecting")
            self.dot.setObjectName("warn")
        else:
            self.dot.setText("● Disconnected")
            self.dot.setObjectName("bad")
        self.dot.style().unpolish(self.dot)
        self.dot.style().polish(self.dot)

    def set_streaming(self, streaming: bool) -> None:
        self.stream.setText("Screen streaming: ON" if streaming else "Screen streaming: OFF")

    def set_banner(self, text: str) -> None:
        self.banner.setText(text)
        self.banner.setVisible(bool(text))

    def show_frame(self, image: QImage, frame: VideoFrame) -> None:
        self.screen.set_frame(image, frame)

    def focus_screen(self) -> None:
        self.screen.setFocus()

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.toLocalFile()]
        if paths:
            self.files_dropped.emit(paths)
