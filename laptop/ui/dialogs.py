"""Small dialogs: pairing code, settings, and clipboard."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QPlainTextEdit,
)

from laptop.config.settings import QUALITY_TO_JPEG, AppConfig


class PairingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pair Android Device")
        self.setModal(True)
        self.setMinimumWidth(380)
        title = QLabel("Pair Android Device")
        title.setObjectName("headline")
        title.setAlignment(Qt.AlignCenter)
        self.code = QLabel("------")
        self.code.setObjectName("pairCode")
        self.code.setAlignment(Qt.AlignCenter)
        hint = QLabel("Enter this code on your phone, then tap Pair.")
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignCenter)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(self.code)
        layout.addWidget(hint)
        layout.addWidget(cancel)

    def set_code(self, code: str) -> None:
        self.code.setText(code)


class SettingsDialog(QDialog):
    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(420)
        self.name = QLineEdit(config.device_name)
        self.width = QSpinBox()
        self.width.setRange(240, 1920)
        self.width.setValue(config.max_width)
        self.height = QSpinBox()
        self.height.setRange(240, 1920)
        self.height.setValue(config.max_height)
        self.fps = QSpinBox()
        self.fps.setRange(5, 30)
        self.fps.setValue(config.fps)
        self.quality = QComboBox()
        self.quality.addItems(["low", "medium", "high"])
        if config.quality_label in QUALITY_TO_JPEG:
            self.quality.setCurrentText(config.quality_label)
        else:
            self.quality.setCurrentText("medium")
        self.reconnect = QCheckBox("Reconnect when Wi-Fi drops")
        self.reconnect.setChecked(config.reconnect)
        self.clipboard = QCheckBox("Send laptop clipboard text to the phone")
        self.clipboard.setChecked(config.clipboard_auto)
        form = QFormLayout()
        form.addRow("Laptop name", self.name)
        form.addRow("Max width", self.width)
        form.addRow("Max height", self.height)
        form.addRow("Frames per second", self.fps)
        form.addRow("Quality", self.quality)
        buttons = QHBoxLayout()
        save = QPushButton("Save")
        save.setObjectName("primary")
        save.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(save)
        buttons.addWidget(cancel)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.reconnect)
        layout.addWidget(self.clipboard)
        note = QLabel("Width and height are a maximum box. The phone keeps its own aspect ratio.")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addLayout(buttons)

    def apply_to(self, config: AppConfig) -> None:
        config.device_name = self.name.text().strip()[:40] or "My PC"
        config.max_width = self.width.value()
        config.max_height = self.height.value()
        config.fps = self.fps.value()
        config.quality_label = self.quality.currentText()
        config.jpeg_quality = QUALITY_TO_JPEG[config.quality_label]
        config.reconnect = self.reconnect.isChecked()
        config.clipboard_auto = self.clipboard.isChecked()


class ClipboardDialog(QDialog):
    send_requested = Signal(str)
    pull_requested = Signal()

    def __init__(self, auto_sync: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Clipboard")
        self.setMinimumSize(460, 320)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("Clipboard text")
        send = QPushButton("Paste into the phone")
        send.setObjectName("primary")
        send.clicked.connect(self._send)
        pull = QPushButton("Get from phone")
        pull.clicked.connect(self.pull_requested.emit)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addWidget(send)
        row.addWidget(pull)
        row.addWidget(close)
        note = QLabel(
            "Automatic sync is on. Text you copy on the laptop is sent to the phone over Wi-Fi."
            if auto_sync
            else "Automatic sync is off. Use the buttons to copy text yourself."
        )
        note.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addWidget(note)
        layout.addWidget(self.editor)
        layout.addLayout(row)

    def set_text(self, text: str) -> None:
        self.editor.setPlainText(text)

    def _send(self) -> None:
        self.send_requested.emit(self.editor.toPlainText())
