"""Desktop window that discovers the phone, shows it, and sends input."""

from __future__ import annotations

import logging
import sys
import time
from collections import deque
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from laptop.config.settings import AppConfig, save_config
from laptop.network.addresses import is_allowed_host
from laptop.network.connection import NetworkController
from laptop.network.installer import InstallerServer
from laptop.network.pairing import PairedStore
from laptop.streaming.renderer import jpeg_to_qimage
from laptop.ui.connection_view import ConnectionView
from laptop.ui.device_view import DeviceView
from laptop.ui.dialogs import ClipboardDialog, PairingDialog, SettingsDialog

log = logging.getLogger(__name__)

STYLE = """
QMainWindow, QDialog, QWidget { background: #f4f0e8; color: #1c1917; }
QLabel { color: #1c1917; background: transparent; }
QLabel#headline { font-size: 26px; font-weight: 700; color: #1c1917; }
QLabel#cardTitle { font-size: 16px; font-weight: 600; color: #1c1917; }
QLabel#section { font-size: 13px; font-weight: 700; color: #44403c; }
QLabel#subhead { color: #44403c; }
QLabel#good { color: #166534; font-weight: 700; }
QLabel#warn { color: #9a3412; font-weight: 700; }
QLabel#bad { color: #9f2d2d; font-weight: 700; }
QLabel#banner {
    background: #9f2d2d;
    color: white;
    border-radius: 10px;
    padding: 10px 12px;
}
QLabel#installUrl {
    font-size: 22px;
    font-weight: 700;
    color: #0f6e6e;
}
QLabel#pairCode {
    font-family: Consolas, "Courier New", monospace;
    font-size: 42px;
    letter-spacing: 8px;
    color: #0f6e6e;
    background: #ffffff;
    border: 1px solid #d6d3d1;
    border-radius: 12px;
    padding: 12px 8px;
}
QFrame#card, QFrame#panel {
    background: #ffffff;
    border: 1px solid #e4ddd2;
    border-radius: 14px;
}
QFrame#bezel {
    background: #1c1917;
    border-radius: 18px;
}
QPushButton {
    background: #ffffff;
    color: #1c1917;
    border: 1px solid #d6d3d1;
    border-radius: 10px;
    padding: 8px 14px;
    min-height: 22px;
}
QPushButton:hover { background: #f5f0e8; }
QPushButton#primary {
    background: #0f6e6e;
    color: #ffffff;
    border: none;
    font-weight: 600;
    padding: 8px 18px;
}
QPushButton#primary:hover { background: #0c5858; }
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit {
    background: #ffffff;
    color: #1c1917;
    border: 1px solid #d6d3d1;
    border-radius: 10px;
    padding: 8px 10px;
    min-height: 22px;
    selection-background-color: #0f6e6e;
    selection-color: #ffffff;
}
QSpinBox { min-width: 88px; }
QStatusBar { background: #efeae3; color: #44403c; }
QStatusBar QLabel { color: #44403c; }
QProgressBar {
    border: 1px solid #d6d3d1;
    border-radius: 8px;
    background: #ffffff;
    color: #1c1917;
    text-align: center;
    min-height: 18px;
}
QProgressBar::chunk { background: #0f6e6e; border-radius: 7px; }
QScrollArea { background: transparent; border: none; }
QCheckBox { color: #1c1917; background: transparent; spacing: 8px; }
"""


def _install_apk() -> Path:
    root = Path(__file__).resolve().parents[2]
    for name in ("PhoneRemote3.apk", "PhoneRemote2.apk", "PhoneRemote.apk"):
        candidate = root / name
        if candidate.is_file():
            return candidate
    return root / "PhoneRemote3.apk"


def format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


class MainWindow(QMainWindow):
    def __init__(self, config: AppConfig, store: PairedStore, download_dir: Path):
        super().__init__()
        self.config = config
        self.store = store
        self.download_dir = download_dir
        self.setWindowTitle("Phone Remote Control")
        self.resize(980, 820)
        self._in_session = False
        self._phone_name = "Android phone"
        self._host = ""
        self._streaming = False
        self._shown_errors: set[str] = set()
        self._frame_times: deque[float] = deque()
        self._last_clip = QApplication.clipboard().text() or ""
        self._pairing: PairingDialog | None = None
        self._clipboard_dialog: ClipboardDialog | None = None

        self.connection_view = ConnectionView(config.port)
        self.device_view = DeviceView()
        apk = _install_apk()
        self.installer = InstallerServer(apk)
        self.connection_view.set_install_url(self.installer.start())
        self.stack = QStackedWidget()
        self.stack.addWidget(self.connection_view)
        self.stack.addWidget(self.device_view)
        self.transfer_label = QLabel("")
        self.transfer_bar = QProgressBar()
        self.transfer_bar.setRange(0, 100)
        self.transfer_label.setVisible(False)
        self.transfer_bar.setVisible(False)
        transfer_row = QHBoxLayout()
        transfer_row.addWidget(self.transfer_label, 1)
        transfer_row.addWidget(self.transfer_bar, 1)
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stack, 1)
        layout.addLayout(transfer_row)
        self.setCentralWidget(root)
        self.fps_label = QLabel("FPS: —")
        self.latency_label = QLabel("Latency: —")
        self.network_label = QLabel("Wi-Fi")
        self.statusBar().addPermanentWidget(self.fps_label)
        self.statusBar().addPermanentWidget(self.latency_label)
        self.statusBar().addPermanentWidget(self.network_label)
        self.statusBar().showMessage("Wi-Fi only. The internet is not used.")

        self.controller = NetworkController(config, store, download_dir)
        self._wire()
        self.controller.start()
        QApplication.clipboard().dataChanged.connect(self._on_local_clipboard)

    def _wire(self) -> None:
        self.connection_view.connect_requested.connect(self._connect)
        self.connection_view.settings_requested.connect(self._open_settings)
        self.connection_view.forget_requested.connect(self._forget)
        self.device_view.pointer.connect(self.controller.send_mouse)
        self.device_view.key_typed.connect(self.controller.send_key)
        self.device_view.nav_requested.connect(self.controller.send_nav)
        self.device_view.file_requested.connect(self._pick_files)
        self.device_view.files_dropped.connect(self._send_paths)
        self.device_view.clipboard_requested.connect(self._open_clipboard)
        self.device_view.settings_requested.connect(self._open_settings)
        self.device_view.disconnect_requested.connect(self._disconnect)
        self.controller.devices_changed.connect(self.connection_view.set_devices)
        self.controller.pairing_required.connect(self._show_pairing)
        self.controller.pairing_failed.connect(self._pairing_failed)
        self.controller.authed.connect(self._on_authed)
        self.controller.disconnected.connect(self._on_disconnected)
        self.controller.frame_received.connect(self._on_frame)
        self.controller.status_received.connect(self._on_status)
        self.controller.latency_received.connect(self._on_latency)
        self.controller.protocol_error.connect(self._on_error)
        self.controller.file_progress.connect(self._on_file_progress)
        self.controller.file_offer.connect(self._on_file_offer, Qt.QueuedConnection)
        self.controller.clipboard_received.connect(self._on_phone_clipboard)

    def _connect(self, host: str, port: int) -> None:
        if not is_allowed_host(host):
            QMessageBox.warning(
                self,
                "Phone Remote",
                "Enter a private Wi-Fi address such as 192.168.1.20.\nNames and public addresses are not used.",
            )
            return
        self._host = host
        self._shown_errors.clear()
        self.connection_view.set_status(f"Connecting to {host}:{port}…")
        self.controller.connect_to(host, port)

    def _disconnect(self) -> None:
        self._in_session = False
        self.controller.disconnect_phone()
        self._close_pairing()
        self.stack.setCurrentWidget(self.connection_view)
        self.connection_view.set_status("Disconnected")
        self.device_view.set_banner("")
        self.statusBar().showMessage("Disconnected")

    def _forget(self) -> None:
        self.store.forget_all()
        QMessageBox.information(
            self,
            "Phone Remote",
            "The saved phone was forgotten. The next connection will ask you to pair again.",
        )

    def _show_pairing(self, code: str) -> None:
        if self._pairing is None:
            self._pairing = PairingDialog(self)
            self._pairing.rejected.connect(self._pairing_cancelled)
        self._pairing.set_code(code)
        self._pairing.show()
        self._pairing.raise_()
        self._pairing.activateWindow()

    def _pairing_cancelled(self) -> None:
        if self._in_session:
            return
        self._disconnect()

    def _pairing_failed(self, message: str) -> None:
        QMessageBox.warning(self, "Phone Remote", message)

    def _close_pairing(self) -> None:
        if self._pairing is not None:
            self._pairing.blockSignals(True)
            self._pairing.close()
            self._pairing.blockSignals(False)
            self._pairing = None

    def _on_authed(self, info: dict) -> None:
        self._in_session = True
        self._phone_name = str(info.get("phone_name") or "Android phone")
        self._host = str(info.get("host") or self._host)
        self._close_pairing()
        self.device_view.set_connection(self._phone_name, self._host, True, False)
        self.device_view.set_streaming(False)
        self.device_view.set_banner("")
        self.stack.setCurrentWidget(self.device_view)
        self.device_view.focus_screen()
        self.statusBar().showMessage("Connected over Wi-Fi")
        log.info("Showing %s at %s", self._phone_name, self._host)

    def _on_disconnected(self, message: str, reconnecting: bool) -> None:
        if self._in_session and reconnecting:
            self.device_view.set_connection(self._phone_name, self._host, False, True)
            self.device_view.set_banner(message)
            self.device_view.set_streaming(False)
            self.statusBar().showMessage("Attempting to reconnect…")
            return
        if self._in_session and not reconnecting:
            self._in_session = False
            self.stack.setCurrentWidget(self.connection_view)
        self._close_pairing()
        self.connection_view.set_status(message)
        self.device_view.set_banner("")
        if not reconnecting:
            self.statusBar().showMessage("Disconnected")

    def _on_frame(self, frame) -> None:
        image = jpeg_to_qimage(frame.jpeg)
        if image is None:
            log.warning("Could not decode a screen frame")
            return
        self.device_view.show_frame(image, frame)
        if not self._streaming:
            self._streaming = True
            self.device_view.set_streaming(True)
        now = time.monotonic()
        self._frame_times.append(now)
        while self._frame_times and now - self._frame_times[0] > 1:
            self._frame_times.popleft()
        self.fps_label.setText(f"FPS: {len(self._frame_times)}")

    def _on_status(self, status: dict) -> None:
        streaming = bool(status.get("streaming") or status.get("sharing"))
        self._streaming = streaming
        self.device_view.set_streaming(streaming)
        if status.get("accessibility") is False and self._in_session:
            self.device_view.set_banner(
                "Touch, keyboard, and Back/Home/Recents need the Phone Remote accessibility service. "
                "Open the Android app and tap Enable accessibility."
            )
        elif streaming:
            self.device_view.set_banner("")

    def _on_latency(self, milliseconds: int) -> None:
        self.latency_label.setText(f"Latency: {milliseconds} ms")

    def _on_error(self, code: str, message: str) -> None:
        self.device_view.set_banner(message)
        if code in self._shown_errors:
            return
        self._shown_errors.add(code)
        QMessageBox.warning(self, "Phone Remote", message)

    def _on_file_offer(self, offer: dict, decision) -> None:
        size = format_size(int(offer.get("size") or 0))
        answer = QMessageBox.question(
            self,
            "Transfer to laptop",
            f"Receive {offer.get('name')} ({size}) from the phone?",
        )
        if not decision.done():
            decision.set_result(answer == QMessageBox.Yes)

    def _on_file_progress(self, event: dict) -> None:
        state = event.get("state")
        name = event.get("name") or "file"
        size = int(event.get("size") or 0)
        done = int(event.get("bytes") or 0)
        if state == "error":
            self.transfer_label.setText(event.get("message") or "Transfer failed.")
            self.transfer_label.setVisible(True)
            self.transfer_bar.setVisible(False)
            return
        if state == "done":
            where = event.get("message") or ""
            if event.get("direction") == "receive" and where:
                text = f"Saved {name} to {where}"
            elif event.get("direction") == "send":
                text = f"Sent {name} to the phone"
            else:
                text = f"Finished {name}"
            self.transfer_label.setText(text)
            self.transfer_bar.setValue(100)
            self.transfer_label.setVisible(True)
            self.transfer_bar.setVisible(True)
            return
        percent = int(done * 100 / size) if size else 0
        direction = "to the phone" if event.get("direction") == "send" else "from the phone"
        self.transfer_label.setText(f"{name}  {format_size(done)} / {format_size(size)}  {direction}")
        self.transfer_bar.setValue(max(0, min(100, percent)))
        self.transfer_label.setVisible(True)
        self.transfer_bar.setVisible(True)

    def _pick_files(self) -> None:
        paths, _selected = QFileDialog.getOpenFileNames(self, "Transfer to phone")
        self._send_paths(paths)

    def _send_paths(self, paths: list[str]) -> None:
        for path in paths:
            if path:
                self.controller.send_file(path)

    def _open_clipboard(self) -> None:
        if self._clipboard_dialog is None:
            self._clipboard_dialog = ClipboardDialog(self.config.clipboard_auto, self)
            self._clipboard_dialog.send_requested.connect(self._send_clipboard_text)
            self._clipboard_dialog.pull_requested.connect(self.controller.pull_clipboard)
        self._clipboard_dialog.set_text(QApplication.clipboard().text() or "")
        self._clipboard_dialog.show()
        self._clipboard_dialog.raise_()

    def _send_clipboard_text(self, text: str) -> None:
        self._last_clip = text
        self.controller.send_clipboard(text)

    def _on_phone_clipboard(self, text: str) -> None:
        self._last_clip = text
        QApplication.clipboard().setText(text)
        if self._clipboard_dialog is not None and self._clipboard_dialog.isVisible():
            self._clipboard_dialog.set_text(text)
        log.info("Clipboard received from the phone (%s characters)", len(text))

    def _on_local_clipboard(self) -> None:
        if not self._in_session or not self.config.clipboard_auto:
            return
        text = QApplication.clipboard().text() or ""
        if text == self._last_clip or len(text) > 256_000:
            return
        self._last_clip = text
        self.controller.send_clipboard(text)
        log.info("Clipboard sent to the phone (%s characters)", len(text))

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.config, self)
        if dialog.exec() != SettingsDialog.Accepted:
            return
        dialog.apply_to(self.config)
        save_config(self.config)
        self.connection_view.port.setValue(self.config.port)
        if self._in_session:
            self.controller.send_stream_config()
        if self._clipboard_dialog is not None:
            self._clipboard_dialog.close()
            self._clipboard_dialog = None

    def closeEvent(self, event) -> None:
        self.installer.stop()
        self.controller.shutdown()
        super().closeEvent(event)


def apply_theme(app: QApplication) -> None:
    """Force dark ink on a light window. Windows dark mode otherwise paints white text."""
    app.setStyle("Fusion")
    palette = QPalette()
    ink = QColor("#1c1917")
    paper = QColor("#f4f0e8")
    card = QColor("#ffffff")
    palette.setColor(QPalette.Window, paper)
    palette.setColor(QPalette.WindowText, ink)
    palette.setColor(QPalette.Base, card)
    palette.setColor(QPalette.AlternateBase, paper)
    palette.setColor(QPalette.Text, ink)
    palette.setColor(QPalette.Button, card)
    palette.setColor(QPalette.ButtonText, ink)
    palette.setColor(QPalette.Highlight, QColor("#0f6e6e"))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.PlaceholderText, QColor("#78716c"))
    app.setPalette(palette)
    app.setStyleSheet(STYLE)


def run_app(config: AppConfig, store: PairedStore, download_dir: Path) -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Phone Remote")
    app.setFont(QFont("Segoe UI", 10))
    apply_theme(app)
    window = MainWindow(config, store, download_dir)
    window.show()
    app.exec()
