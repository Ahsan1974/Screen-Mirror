"""The first screen: phones found on Wi-Fi, plus a manual IP."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class ConnectionView(QWidget):
    connect_requested = Signal(str, int)
    settings_requested = Signal()
    forget_requested = Signal()

    def __init__(self, default_port: int, parent=None):
        super().__init__(parent)
        self._rows = QVBoxLayout()
        self._rows.setContentsMargins(0, 0, 0, 0)
        self._rows.setSpacing(10)
        holder = QWidget()
        holder.setLayout(self._rows)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setWidget(holder)
        self.scroll.viewport().setAutoFillBackground(False)

        self.status = QLabel("Searching for phones…")
        self.status.setObjectName("subhead")
        self.status.setWordWrap(True)

        self.empty = QFrame()
        self.empty.setObjectName("card")
        empty_layout = QVBoxLayout(self.empty)
        empty_layout.setContentsMargins(18, 16, 18, 16)
        empty_layout.setSpacing(6)
        missing = QLabel("No phone found.")
        missing.setObjectName("cardTitle")
        empty_layout.addWidget(missing)
        empty_layout.addWidget(QLabel("Make sure:"))
        for line in (
            "Phone Wi-Fi is on",
            "Laptop Wi-Fi is on",
            "Both are on the same network",
            "The Phone Remote app is open on the phone",
        ):
            row = QLabel(f"✓  {line}")
            row.setObjectName("subhead")
            empty_layout.addWidget(row)

        self.list_title = QLabel("Available devices")
        self.list_title.setObjectName("section")

        self.ip = QLineEdit()
        self.ip.setPlaceholderText("192.168.1.20")
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(default_port)
        manual = QPushButton("Connect")
        manual.setObjectName("primary")
        manual.clicked.connect(self._manual_connect)
        ip_row = QHBoxLayout()
        ip_label = QLabel("Phone IP")
        ip_label.setObjectName("section")
        port_label = QLabel("Port")
        port_label.setObjectName("section")
        ip_row.addWidget(ip_label)
        ip_row.addWidget(self.ip, 1)
        ip_row.addWidget(port_label)
        ip_row.addWidget(self.port)
        ip_row.addWidget(manual)

        manual_card = QFrame()
        manual_card.setObjectName("panel")
        manual_layout = QVBoxLayout(manual_card)
        manual_layout.setContentsMargins(18, 16, 18, 16)
        manual_layout.setSpacing(10)
        manual_title = QLabel("Manual connection")
        manual_title.setObjectName("cardTitle")
        manual_hint = QLabel("Type the IP shown at the top of the phone app. The port is 8765 unless you changed it.")
        manual_hint.setObjectName("subhead")
        manual_hint.setWordWrap(True)
        manual_layout.addWidget(manual_title)
        manual_layout.addWidget(manual_hint)
        manual_layout.addLayout(ip_row)

        settings = QPushButton("Settings")
        settings.clicked.connect(self.settings_requested.emit)
        forget = QPushButton("Forget paired phone")
        forget.clicked.connect(self.forget_requested.emit)
        tools = QHBoxLayout()
        tools.addWidget(settings)
        tools.addWidget(forget)
        tools.addStretch(1)

        title = QLabel("Phone Remote")
        title.setObjectName("headline")
        subtitle = QLabel("View and control your Android phone on this Wi-Fi. No internet and no USB.")
        subtitle.setWordWrap(True)
        subtitle.setObjectName("subhead")

        install = QFrame()
        install.setObjectName("panel")
        install_layout = QVBoxLayout(install)
        install_layout.setContentsMargins(18, 16, 18, 16)
        install_layout.setSpacing(8)
        install_title = QLabel("1. Put the app on your phone")
        install_title.setObjectName("cardTitle")
        install_hint = QLabel(
            "On the phone, open Chrome and type the address below. "
            "Tap Download, open the file, then tap Install. Do not use WhatsApp."
        )
        install_hint.setObjectName("subhead")
        install_hint.setWordWrap(True)
        self.install_url = QLabel("Finding this laptop’s Wi-Fi address…")
        self.install_url.setObjectName("installUrl")
        self.install_url.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.install_url.setWordWrap(True)
        install_layout.addWidget(install_title)
        install_layout.addWidget(install_hint)
        install_layout.addWidget(self.install_url)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 22)
        layout.setSpacing(14)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(install)
        layout.addWidget(self.status)
        layout.addWidget(self.list_title)
        layout.addWidget(self.scroll)
        layout.addWidget(self.empty)
        layout.addWidget(manual_card)
        layout.addLayout(tools)
        layout.addStretch(1)
        self.set_devices([])

    def set_install_url(self, url: str) -> None:
        if url:
            self.install_url.setText(url)
        else:
            self.install_url.setText("Connect the laptop to Wi-Fi, then open this window again.")

    def set_status(self, text: str) -> None:
        self.status.setText(text)

    def set_devices(self, devices: list) -> None:
        while self._rows.count():
            item = self._rows.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if not devices:
            self.empty.setVisible(True)
            self.scroll.setVisible(False)
            self.list_title.setVisible(False)
            return
        self.empty.setVisible(False)
        self.scroll.setVisible(True)
        self.list_title.setVisible(True)
        self.status.setText(f"Found {len(devices)} phone{'s' if len(devices) != 1 else ''}.")
        for device in devices:
            self._rows.addWidget(self._card(device))
        self._rows.addStretch(1)

    def _card(self, device) -> QFrame:
        frame = QFrame()
        frame.setObjectName("card")
        name = QLabel(device.name)
        name.setObjectName("cardTitle")
        address = QLabel(f"{device.host}:{device.port}")
        address.setObjectName("subhead")
        state = QLabel("Available")
        state.setObjectName("good")
        button = QPushButton("Connect")
        button.setObjectName("primary")
        host = device.host
        port = device.port
        button.clicked.connect(lambda checked=False, h=host, p=port: self.connect_requested.emit(h, p))
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(name)
        text.addWidget(address)
        text.addWidget(state)
        row = QHBoxLayout(frame)
        row.setContentsMargins(16, 14, 16, 14)
        row.addLayout(text, 1)
        row.addWidget(button, alignment=Qt.AlignVCenter)
        return frame

    def _manual_connect(self) -> None:
        self.connect_requested.emit(self.ip.text().strip(), self.port.value())
