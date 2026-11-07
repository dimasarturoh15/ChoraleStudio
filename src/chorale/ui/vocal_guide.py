"""Wizard 'Persiapan Rekam Vokal' (mockup: harmonisatb_studio_recording_setup_guide; isi: PRD bagian 9)."""

from __future__ import annotations

import time
from collections import deque

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from chorale.ui import icons, theme
from chorale.ui.overlay import ModalOverlay
from chorale.ui.theme import COLORS
from chorale.ui.widgets import button, hbox, label, refresh_style, vbox

TARGET_LOW_DB, TARGET_HIGH_DB = -14.0, -10.0
PEAK_HOLD_S = 3.0

STEP_TITLES = ("Posisi Penyanyi", "Atur Gain Mic", "Atur Headphone")
STEP_ITEMS = (
    ("Bentuk setengah lingkaran menghadap mic, 2–4 penyanyi.",
     "Jarak 35–45 cm dari mic, sama rata untuk semua orang.",
     "Pasang pop filter sekitar 7 cm di depan mic.",
     "Semua penyanyi aktif memakai headphone closed-back."),
    ("Nyalakan tombol +48V pada sound card.",
     "Minta kelompok menyanyikan bagian paling keras dari lagu.",
     "Putar kenop Gain sampai meter berada di area target.",
     "Jangan ubah Gain selama merekam suara ini."),
    ("Nyalakan tombol direct monitor (ON) agar penyanyi mendengar suaranya sendiri, lalu atur volume agar nyaman.",
     "Atur volume headphone secukupnya agar tidak bocor ke mic.",
     "Suara penyanyi tidak diputar oleh aplikasi; penyanyi mendengarnya lewat tombol direct monitor.",
     "Tekan Putar Piano untuk mencoba volume headphone."),
)
HIGHLIGHT = (None, 2, 0)
MSG_REFERENCE_CABLE = ("Kanal acuan aktif: pastikan kabel dari Output ke Input {n} terpasang dengan gain kecil, "
                       "agar setiap take sejajar otomatis dengan piano.")


def level_status(peak_db: float) -> tuple[str, str]:
    """(teks, tingkat) untuk puncak 3 detik terakhir: tingkat 'pas', 'pelan', 'keras', 'kosong'."""
    if peak_db < -50:
        return "Belum ada suara", "kosong"
    if peak_db < TARGET_LOW_DB:
        return "Terlalu pelan — naikkan Gain", "pelan"
    if peak_db <= TARGET_HIGH_DB:
        return "Level sudah pas", "pas"
    if peak_db <= -3:
        return "Agak keras — kecilkan Gain sedikit", "keras"
    return "Terlalu keras — kecilkan Gain", "keras"


class StepIndicator(QWidget):
    """Tiga lingkaran langkah dihubungkan garis, dengan label di bawahnya."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current = 0
        self.setFixedHeight(84)

    def set_step(self, i: int) -> None:
        self.current = i
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        xs = [w * (i + 0.5) / 3 for i in range(3)]
        y = 22
        for i in range(2):
            color = COLORS["blue"] if i < self.current else COLORS["border"]
            p.setPen(QPen(QColor(color), 2))
            p.drawLine(QPointF(xs[i] + 24, y), QPointF(xs[i + 1] - 24, y))
        for i, x in enumerate(xs):
            done, active = i < self.current, i == self.current
            if done:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(COLORS["green"]))
            elif active:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(COLORS["blue"]))
            else:
                p.setPen(QPen(QColor(COLORS["text2"]), 2))
                p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(x, y), 20, 20)
            if done:
                p.drawPixmap(int(x - 11), int(y - 11), icons.pixmap("check", "#FFFFFF", 22, 3.0))
            else:
                p.setPen(QColor("#FFFFFF" if active else COLORS["text2"]))
                p.setFont(theme.font(15, QFont.DemiBold))
                p.drawText(QRectF(x - 20, y - 20, 40, 40), Qt.AlignCenter, str(i + 1))
            p.setPen(QColor(COLORS["text"] if active else COLORS["text2"]))
            p.setFont(theme.font(16, QFont.DemiBold if active else QFont.Normal))
            p.drawText(QRectF(x - 140, 50, 280, 30), Qt.AlignCenter, f"{i + 1} {STEP_TITLES[i]}")
        p.end()


class TargetMeter(QWidget):
    """Meter horizontal dengan Area Target -14..-10 dBFS."""

    FLOOR = -48.0
    MARKS = ((-42, "-42"), (-24, "-24"), (-14, "-14"), (-10, "-10"), (-3, "-3"), (0, "0 dB"))

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(118)
        self.db = -120.0

    def set_db(self, db: float) -> None:
        self.db = db
        self.update()

    def _x(self, db: float, left: float, width: float) -> float:
        return left + max(0.0, min(1.0, (db - self.FLOOR) / -self.FLOOR)) * width

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        left, width = 4.0, self.width() - 8.0
        p.setFont(theme.font(13, mono=True))
        fm = p.fontMetrics()
        limit = float(self.width())  # label ditaruh dari kanan; yang bertabrakan digeser ke kiri
        for db, text in reversed(self.MARKS):
            tw = fm.horizontalAdvance(text)
            x = self._x(db, left, width) - (tw if db == 0 else tw / 2)
            x = max(0.0, min(limit - tw, x))
            color = COLORS["red"] if db == 0 else (COLORS["blue"] if db in (-14, -10) else COLORS["text2"])
            p.setPen(QColor(color))
            p.drawText(QRectF(x, 0, tw + 1, 18), Qt.AlignLeft | Qt.AlignVCenter, text)
            limit = x - 8
        bar = QRectF(left, 30, width, 44)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(COLORS["app"]))
        p.drawRoundedRect(bar, 6, 6)
        inner = bar.adjusted(6, 6, -6, -6)
        for lo, hi, color in ((self.FLOOR, -12, COLORS["green"]), (-12, -3, COLORS["yellow"]), (-3, 0, COLORS["red"])):
            off = QColor(color)
            off.setAlphaF(0.18)
            x0, x1 = self._x(lo, inner.left(), inner.width()), self._x(hi, inner.left(), inner.width())
            p.setBrush(off)
            p.drawRect(QRectF(x0, inner.top(), x1 - x0, inner.height()))
            if self.db > lo:
                p.setBrush(QColor(color))
                xe = self._x(min(self.db, hi), inner.left(), inner.width())
                p.drawRect(QRectF(x0, inner.top(), xe - x0, inner.height()))
        t0, t1 = self._x(TARGET_LOW_DB, inner.left(), inner.width()), self._x(TARGET_HIGH_DB, inner.left(), inner.width())
        p.setPen(QPen(QColor(COLORS["blue"]), 2))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(t0, bar.top() - 2, t1 - t0, bar.height() + 4), 4, 4)
        p.setFont(theme.font(14))
        p.setPen(QColor(COLORS["text2"]))
        p.drawText(QRectF(left, 84, 200, 24), Qt.AlignLeft | Qt.AlignVCenter, "Aman")
        p.drawText(QRectF(self.width() - 204, 84, 200, 24), Qt.AlignRight | Qt.AlignVCenter, "Klip")
        p.setPen(QColor(COLORS["blue"]))
        text = "Optimal (-14 s/d -10 dBFS)"
        tw = p.fontMetrics().horizontalAdvance(text)
        klip = p.fontMetrics().horizontalAdvance("Klip")
        x = min((t0 + t1) / 2 - tw / 2, self.width() - 4 - klip - 16 - tw)
        p.drawText(QRectF(x, 84, tw + 2, 24), Qt.AlignLeft | Qt.AlignVCenter, text)
        p.end()


class PositionDiagram(QWidget):
    """Gambar sederhana: penyanyi setengah lingkaran di depan mic."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(240)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        mic = QPointF(w / 2, h - 40)
        radius = min(w * 0.38, h - 80)
        p.setPen(QPen(QColor(COLORS["border"]), 2, Qt.DashLine))
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(mic.x() - radius, mic.y() - radius, 2 * radius, 2 * radius), 20 * 16, 140 * 16)
        import math
        for i in range(4):
            angle = math.radians(35 + i * 110 / 3)
            pt = QPointF(mic.x() + radius * math.cos(angle), mic.y() - radius * math.sin(angle))
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(COLORS["blue"]))
            p.drawEllipse(pt, 13, 13)
        p.setBrush(QColor(COLORS["text"]))
        p.drawEllipse(mic, 9, 9)
        p.setPen(QPen(QColor(COLORS["text2"]), 1))
        p.drawLine(mic, QPointF(mic.x(), mic.y() - radius + 16))
        p.setFont(theme.font(14, mono=True))
        p.setPen(QColor(COLORS["text"]))
        p.drawText(QRectF(mic.x() + 8, mic.y() - radius / 2 - 12, 140, 24), Qt.AlignLeft | Qt.AlignVCenter,
                   "35–45 cm")
        p.setFont(theme.font(14))
        p.setPen(QColor(COLORS["text2"]))
        p.drawText(QRectF(0, mic.y() + 12, w, 24), Qt.AlignCenter, "Mic + pop filter (±7 cm)")
        p.end()


class VocalGuideOverlay(ModalOverlay):
    """Wizard 3 langkah sebelum rekam vokal pertama di proyek."""

    finished = Signal()
    playPianoRequested = Signal()

    def __init__(self, parent: QWidget):
        super().__init__(parent, 1240)
        self.step = 0
        self._history: deque[tuple[float, float]] = deque()

        close = button("", "icon", "close", COLORS["text2"], 22)
        close.clicked.connect(self.close_overlay)
        self.indicator = StepIndicator()
        sep = QFrame()
        sep.setObjectName("separator")

        self.items_stack = QStackedWidget()
        self._item_frames: list[list[QFrame]] = []
        for s, items in enumerate(STEP_ITEMS):
            page = QWidget()
            col = QVBoxLayout(page)
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(12)
            frames = []
            for i, text in enumerate(items):
                f = QFrame()
                f.setObjectName("guideItem")
                f.setProperty("active", HIGHLIGHT[s] == i)
                num = label(str(i + 1), "guideNum")
                num.setFixedSize(30, 30)
                num.setAlignment(Qt.AlignCenter)
                num.setProperty("active", HIGHLIGHT[s] == i)
                t = label(text, "guideText")
                t.setWordWrap(True)
                f.setLayout(hbox(vbox(num, None), 16, t, margins=(18, 14, 18, 14)))
                col.addWidget(f)
                frames.append(f)
            if s == len(STEP_ITEMS) - 1:
                self.reference_hint = label("", "hint")
                self.reference_hint.setWordWrap(True)
                self.reference_hint.hide()
                col.addWidget(self.reference_hint)
            col.addStretch(1)
            self._item_frames.append(frames)
            self.items_stack.addWidget(page)

        # Panel kanan per langkah
        self.right_stack = QStackedWidget()
        diagram_panel = QFrame()
        diagram_panel.setObjectName("guidePanel")
        diagram_panel.setLayout(vbox(label("Posisi di Depan Mic", "panelTitle"), 8, PositionDiagram(),
                                     margins=(24, 22, 24, 22)))
        self.meter = TargetMeter()
        self.peak_label = label("Puncak: — dBFS", "peakValue")
        self.status = label("Belum ada suara", "levelStatus")
        self.status.setAlignment(Qt.AlignCenter)
        self.input_hint = label("Input 1 · Mono", "mono")
        sep2 = QFrame()
        sep2.setObjectName("separator")
        level_panel = QFrame()
        level_panel.setObjectName("guidePanel")
        level_panel.setLayout(vbox(
            hbox(label("Pemantauan Level Mic", "panelTitle"), None, self.input_hint), 20,
            self.meter, 12, sep2, 14,
            hbox(vbox(label("Pembacaan Puncak", "secondary"), 6, self.peak_label), None, self.status),
            None, margins=(24, 22, 24, 22)))
        self.piano_btn = button("Putar Piano", "secondary", "play", COLORS["text"], 16)
        self.piano_btn.clicked.connect(self.playPianoRequested)
        phones_text = label("Penyanyi mendengar piano dan suara yang sudah direkam lewat headphone. "
                            "Suara mereka sendiri hanya lewat tombol direct monitor di sound card.", "secondary")
        phones_text.setWordWrap(True)
        phones_panel = QFrame()
        phones_panel.setObjectName("guidePanel")
        phones_panel.setLayout(vbox(label("Uji Dengar", "panelTitle"), 12, phones_text, 20,
                                    hbox(self.piano_btn, None), None, margins=(24, 22, 24, 22)))
        for w in (diagram_panel, level_panel, phones_panel):
            self.right_stack.addWidget(w)

        self.back_btn = button("Kembali", "secondary")
        self.back_btn.setMinimumWidth(130)
        self.back_btn.clicked.connect(self.back)
        self.next_btn = button("Lanjut", "primary")
        self.next_btn.setMinimumWidth(160)
        self.next_btn.setLayoutDirection(Qt.RightToLeft)
        self.next_btn.clicked.connect(self.next)
        sep3 = QFrame()
        sep3.setObjectName("separator")

        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(48, 40, 48, 40)
        lay.setSpacing(0)
        lay.addLayout(hbox(label("Persiapan Rekam Vokal", "h1"), None, close))
        lay.addSpacing(24)
        lay.addWidget(self.indicator)
        lay.addSpacing(12)
        lay.addWidget(sep)
        lay.addSpacing(24)
        body = QHBoxLayout()
        body.setSpacing(48)
        body.addLayout(vbox(label("PANDUAN LANGKAH", "section"), 14, self.items_stack), 11)
        body.addWidget(self.right_stack, 10)
        lay.addLayout(body)
        lay.addSpacing(28)
        lay.addWidget(sep3)
        lay.addSpacing(24)
        lay.addLayout(hbox(self.back_btn, None, self.next_btn))
        self._show_step()

    def open_for(self, input_text: str, reference_input: int | None = None) -> None:
        """reference_input: nomor input kanal acuan (1/2) jika fitur aktif."""
        self.step = 0
        self.input_hint.setText(input_text)
        self.reference_hint.setVisible(reference_input is not None)
        if reference_input is not None:
            self.reference_hint.setText(MSG_REFERENCE_CABLE.format(n=reference_input))
        self._history.clear()
        self._show_step()
        self.open()

    def _show_step(self) -> None:
        self.indicator.set_step(self.step)
        self.items_stack.setCurrentIndex(self.step)
        self.right_stack.setCurrentIndex(self.step)
        self.back_btn.setText("Batal" if self.step == 0 else "Kembali")
        last = self.step == len(STEP_TITLES) - 1
        self.next_btn.setText("Mulai Rekam" if last else "Lanjut")
        self.next_btn.setIcon(icons.icon("mic" if last else "chevron_right", "#FFFFFF", 20))
        self.recenter()

    def back(self) -> None:
        if self.step == 0:
            self.close_overlay()
        else:
            self.step -= 1
            self._show_step()

    def next(self) -> None:
        if self.step < len(STEP_TITLES) - 1:
            self.step += 1
            self._show_step()
        else:
            self.hide()
            self.finished.emit()

    def update_level(self, peak_db: float) -> None:
        """Diberi level input vokal dari timer layar (30 fps)."""
        now = time.monotonic()
        self._history.append((now, peak_db))
        while self._history and now - self._history[0][0] > PEAK_HOLD_S:
            self._history.popleft()
        hold = max(v for _, v in self._history)
        self.meter.set_db(peak_db)
        self.peak_label.setText(f"Puncak: {hold:.1f} dBFS" if hold > -100 else "Puncak: — dBFS")
        text, level = level_status(hold)
        if self.status.text() != ("✓ " + text if level == "pas" else text):
            self.status.setText("✓ " + text if level == "pas" else text)
            self.status.setProperty("level", level)
            refresh_style(self.status)
