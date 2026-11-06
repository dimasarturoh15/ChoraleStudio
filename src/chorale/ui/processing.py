"""Dialog 'Memproses Produksi' (mockup: harmonisatb_studio_processing_modal)."""

from __future__ import annotations

import threading
import time

from PySide6.QtCore import QRectF, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QFrame, QProgressBar, QVBoxLayout, QWidget

from chorale.dsp.errors import ProcessingCancelled
from chorale.dsp.produce import STEP_LABELS, produce
from chorale.dsp.reverb import ROOM_PRESETS
from chorale.ui import icons, theme
from chorale.ui.overlay import ModalOverlay
from chorale.ui.theme import COLORS
from chorale.ui.widgets import button, hbox, label, refresh_style, vbox

WAITING, RUNNING, DONE, SKIPPED = "menunggu", "berjalan", "selesai", "dilewati"


class ProduceWorker(QThread):
    """Menjalankan produce() di thread terpisah; hasil dikirim lewat sinyal (antrean Qt)."""

    progressed = Signal(int, float)
    succeeded = Signal(object)
    cancelled = Signal()
    failed = Signal(str)

    def __init__(self, project, parent=None, produce_fn=produce):
        super().__init__(parent)
        self.project = project
        self.cancel_event = threading.Event()
        self._produce = produce_fn

    def run(self) -> None:
        try:
            result = self._produce(self.project, progress=self.progressed.emit, cancel=self.cancel_event,
                                   verify=True)
            self.succeeded.emit(result)
        except ProcessingCancelled:
            self.cancelled.emit()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc) or exc.__class__.__name__)


class StepIcon(QWidget):
    """Ikon status tahap: centang hijau, pemintal biru, lingkaran abu, atau strip (dilewati)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(26, 26)
        self.state = WAITING
        self.angle = 0

    def set_state(self, state: str) -> None:
        self.state = state
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(2, 2, 22, 22)
        if self.state == DONE:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(COLORS["green"]))
            p.drawEllipse(r)
            p.drawPixmap(4, 4, icons.pixmap("check", "#FFFFFF", 18, 3.0))
        elif self.state == RUNNING:
            for i in range(8):
                color = QColor(COLORS["blue"])
                color.setAlphaF(0.25 + 0.75 * ((i + self.angle) % 8) / 7)
                p.setPen(QPen(color, 2.4, Qt.SolidLine, Qt.RoundCap))
                p.save()
                p.translate(13, 13)
                p.rotate(i * 45)
                p.drawLine(0, 5, 0, 10)
                p.restore()
        elif self.state == SKIPPED:
            p.setPen(QPen(QColor(COLORS["gray"]), 2))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(r)
            p.drawPixmap(4, 4, icons.pixmap("minus", COLORS["text2"], 18, 2.4))
        else:
            p.setPen(QPen(QColor(COLORS["gray"]), 2))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(r)
        p.end()


def eta_text(elapsed: float, percent: float) -> str:
    if percent < 3 or elapsed < 1.5:
        return "Menghitung sisa waktu…"
    remaining = elapsed * (100 - percent) / percent
    if remaining < 10:
        return "Sisa kurang dari 10 detik"
    if remaining < 60:
        return f"Sisa sekitar {int(round(remaining / 5) * 5)} detik"
    minutes = remaining / 60
    return f"Sisa sekitar {minutes:.0f} menit" if minutes >= 1.5 else "Sisa sekitar 1 menit"


class ProcessingOverlay(ModalOverlay):
    finished = Signal(object)   # ProduceResult
    cancelled = Signal()

    def __init__(self, parent: QWidget):
        super().__init__(parent, 720)
        self.worker: ProduceWorker | None = None
        self.produce_fn = produce
        self.subtitle = label("", "subtitle")
        self.bar = QProgressBar()
        self.bar.setObjectName("produceBar")
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(12)
        self.percent = label("0%", "percent")
        self.eta = label("", "secondary")
        self.error = label("", "error")
        self.error.setWordWrap(True)
        self.error.hide()
        self.icons: dict[int, StepIcon] = {}
        self.labels: dict[int, object] = {}
        self.skip_notes: dict[int, object] = {}
        steps = QVBoxLayout()
        steps.setSpacing(16)
        for n, text in STEP_LABELS.items():
            icon = StepIcon()
            lab = label(text, "stepLabel")
            note = label("dilewati", "hint")
            note.hide()
            self.icons[n], self.labels[n], self.skip_notes[n] = icon, lab, note
            steps.addLayout(hbox(icon, 14, lab, 10, note, None))
        sep = QFrame()
        sep.setObjectName("separator")
        self.cancel_btn = button("Batalkan", "toolbar")
        self.cancel_btn.setFixedHeight(48)
        self.cancel_btn.setMinimumWidth(140)
        self.cancel_btn.clicked.connect(self.cancel)

        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(44, 40, 44, 36)
        lay.setSpacing(0)
        lay.addWidget(label("Memproses Produksi", "h1"))
        lay.addSpacing(10)
        lay.addWidget(self.subtitle)
        lay.addSpacing(32)
        lay.addLayout(hbox(self.bar, 20, self.percent))
        lay.addSpacing(16)
        lay.addWidget(self.eta)
        lay.addSpacing(28)
        lay.addLayout(steps)
        lay.addSpacing(8)
        lay.addWidget(self.error)
        lay.addSpacing(24)
        lay.addWidget(sep)
        lay.addSpacing(24)
        lay.addLayout(hbox(None, self.cancel_btn))

        self._spin = QTimer(self)
        self._spin.setInterval(90)
        self._spin.timeout.connect(self._rotate)
        self._started = 0.0
        self._last_pct = 0.0

    # ----- mulai & selesai -----
    def start(self, project) -> None:
        room = ROOM_PRESETS[project.room_preset].label
        self.subtitle.setText(f"{project.title} · Ruang: {room}")
        self.bar.setValue(0)
        self.percent.setText("0%")
        self.eta.setText("Menghitung sisa waktu…")
        self.error.hide()
        self.cancel_btn.setEnabled(True)
        self.cancel_btn.setText("Batalkan")
        for n in STEP_LABELS:
            self._set_step(n, WAITING)
        self._started = time.monotonic()
        self._last_pct = 0.0
        self.worker = ProduceWorker(project, self, self.produce_fn)
        self.worker.progressed.connect(self._on_progress)
        self.worker.succeeded.connect(self._on_success)
        self.worker.cancelled.connect(self._on_cancelled)
        self.worker.failed.connect(self._on_failed)
        self.open()
        self._spin.start()
        self.worker.start()

    @property
    def running(self) -> bool:
        return self.worker is not None and self.worker.isRunning()

    def cancel(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel_event.set()
            self.cancel_btn.setEnabled(False)
            self.cancel_btn.setText("Membatalkan…")
        else:
            self.close_overlay()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.cancel()
        else:
            super().keyPressEvent(event)

    def _finish_worker(self) -> None:
        self._spin.stop()
        if self.worker is not None:
            self.worker.wait()
            self.worker.deleteLater()
            self.worker = None

    def _on_success(self, result) -> None:
        self._finish_worker()
        self.hide()
        self.finished.emit(result)

    def _on_cancelled(self) -> None:
        self._finish_worker()
        self.hide()
        self.cancelled.emit()

    def _on_failed(self, message: str) -> None:
        self._finish_worker()
        for n, icon in self.icons.items():
            if icon.state == RUNNING:
                self._set_step(n, WAITING)
        self.error.setText(f"Proses gagal: {message}")
        self.error.show()
        self.eta.setText("")
        self.cancel_btn.setEnabled(True)
        self.cancel_btn.setText("Tutup")
        self.recenter()

    # ----- progres -----
    def _on_progress(self, step: int, percent: float) -> None:
        percent = max(self._last_pct, percent)
        self._last_pct = percent
        self.bar.setValue(int(percent * 10))
        self.percent.setText(f"{int(percent)}%")
        self.eta.setText(eta_text(time.monotonic() - self._started, percent))
        for n in STEP_LABELS:
            if n < step:
                if self.icons[n].state in (WAITING, RUNNING):
                    self._set_step(n, SKIPPED if self.icons[n].state == WAITING and n == 1 else DONE)
            elif n == step:
                self._set_step(n, DONE if percent >= 100 else RUNNING)

    def _set_step(self, n: int, state: str) -> None:
        self.icons[n].set_state(state)
        self.labels[n].setProperty("state", state)
        refresh_style(self.labels[n])
        self.skip_notes[n].setVisible(state == SKIPPED)
        if state == SKIPPED:
            self.skip_notes[n].setToolTip("Peredam derau belum terpasang; tahap ini dilewati.")

    def _rotate(self) -> None:
        for icon in self.icons.values():
            if icon.state == RUNNING:
                icon.angle = (icon.angle + 1) % 8
                icon.update()


__all__ = ["ProcessingOverlay", "ProduceWorker", "eta_text", "QFont", "theme"]
