"""Dialog 'Sound card terputus' (mockup: harmonisatb_studio_device_error)."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from chorale.ui.overlay import ModalOverlay
from chorale.ui.theme import COLORS
from chorale.ui.track_strip import fmt_duration
from chorale.ui.widgets import button, hbox, icon_label, label, vbox


def loss_message(card: str, track_label: str | None, saved_seconds: float) -> str:
    if track_label:
        return (f"Sambungan ke {card} hilang saat merekam. Rekaman {track_label} sampai detik "
                f"{fmt_duration(saved_seconds)} sudah tersimpan dengan aman.")
    return f"Sambungan ke {card} hilang."


class DeviceErrorOverlay(ModalOverlay):
    reconnectRequested = Signal()

    def __init__(self, parent: QWidget):
        super().__init__(parent, 640, accent=COLORS["red"])
        self.title = label("Sound card terputus", "h2")
        self.message = label("", "body")
        self.message.setWordWrap(True)
        self.message.setStyleSheet("font-size: 17px; font-weight: 400;")
        self.hint = label("Periksa kabel USB, lalu tekan Hubungkan Ulang.", "secondary")
        self.hint.setWordWrap(True)
        self.retry_error = label("", "error")
        self.retry_error.setWordWrap(True)
        self.retry_error.hide()
        close = button("Tutup", "secondary")
        close.setMinimumWidth(110)
        close.clicked.connect(self.close_overlay)
        self.reconnect = button("Hubungkan Ulang", "primary")
        self.reconnect.setMinimumWidth(200)
        self.reconnect.clicked.connect(self.reconnectRequested)

        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(40, 36, 40, 36)
        body = vbox(self.title, 12, self.message, 14, self.hint, 8, self.retry_error)
        lay.addLayout(hbox(vbox(icon_label("warning", COLORS["red"], 40), None), 20, body))
        lay.addSpacing(28)
        lay.addLayout(hbox(None, close, 16, self.reconnect))

    def show_loss(self, card: str, track_label: str | None, saved_seconds: float) -> None:
        self.title.setText("Sound card terputus")
        self.message.setText(loss_message(card, track_label, saved_seconds))
        self._open()

    def show_missing(self, message: str) -> None:
        self.title.setText("Sound card tidak ditemukan")
        self.message.setText(message)
        self._open()

    def _open(self) -> None:
        self.retry_error.hide()
        self.reconnect.setEnabled(True)
        self.reconnect.setText("Hubungkan Ulang")
        self.open()

    def set_retrying(self, retrying: bool) -> None:
        self.reconnect.setEnabled(not retrying)
        self.reconnect.setText("Menghubungkan…" if retrying else "Hubungkan Ulang")

    def show_retry_failed(self, message: str) -> None:
        self.set_retrying(False)
        self.retry_error.setText(f"Masih belum tersambung. {message}")
        self.retry_error.show()
        self.recenter()
