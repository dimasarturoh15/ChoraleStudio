"""Bilah track (Piano/Orgen, Bass, Tenor, Alto, Sopran) yang dipakai ulang di layar perekaman."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton, QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QRadioButton, QSizePolicy,
    QSlider, QVBoxLayout, QWidget,
)

from chorale.audio.meter import meter_zone
from chorale.project.model import TRACK_LABELS, VOLUME_MAX_DB, VOLUME_MIN_DB, Take, Track
from chorale.ui import icons, theme
from chorale.ui.theme import COLORS, TRACK_COLORS
from chorale.ui.waveform import WaveformView
from chorale.ui.widgets import button, hbox, label, refresh_style, vbox

CONTROL_WIDTH = 500
ROW_HEIGHT = 112

STATE_EMPTY, STATE_RECORDING, STATE_RECORDED = "kosong", "merekam", "terekam"


def fmt_duration(seconds: float) -> str:
    m, s = divmod(int(round(seconds)), 60)
    return f"{m:02d}:{s:02d}"


def take_time(take: Take) -> str:
    try:
        return datetime.fromisoformat(take.recorded_at).strftime("%H:%M")
    except ValueError:
        return "--:--"


class RecordButton(QAbstractButton):
    """Tombol rekam bulat 72 px: abu (kosong), merah berkedip (merekam), hijau centang (terekam)."""

    SIZE = 72

    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = STATE_EMPTY
        self.blink_on = True
        self.setFixedSize(self.SIZE + 8, self.SIZE + 8)
        self.setCursor(Qt.PointingHandCursor)

    def set_state(self, state: str) -> None:
        self.state = state
        self.setToolTip({STATE_EMPTY: "Rekam", STATE_RECORDING: "Sedang merekam — tekan Stop untuk selesai",
                         STATE_RECORDED: "Rekam ulang (take baru)"}[state])
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QRectF(4, 4, self.SIZE, self.SIZE)
        dim = 1.0 if self.isEnabled() else 0.45
        if self.state == STATE_RECORDING:
            ring = QColor(COLORS["red"])
            ring.setAlphaF(0.35 if self.blink_on else 0.12)
            p.setPen(Qt.NoPen)
            p.setBrush(ring)
            p.drawEllipse(QRectF(0, 0, self.SIZE + 8, self.SIZE + 8))
            red = QColor(COLORS["red"] if self.blink_on else "#B91C1C")
            p.setBrush(red)
            p.drawEllipse(c)
            p.setBrush(QColor("#FFFFFF"))
            p.drawEllipse(c.center(), 10, 10)
        elif self.state == STATE_RECORDED:
            green = QColor(COLORS["green"])
            green.setAlphaF(dim)
            p.setPen(Qt.NoPen)
            p.setBrush(green)
            p.drawEllipse(c)
            p.drawPixmap(c.center().toPoint() - QPoint(16, 16), icons.pixmap("check", "#FFFFFF", 32, 3.0))
        else:
            gray = QColor(COLORS["gray"])
            gray.setAlphaF(dim)
            p.setPen(Qt.NoPen)
            p.setBrush(gray)
            p.drawEllipse(c)
            white = QColor("#FFFFFF")
            white.setAlphaF(0.95 * dim)
            p.setBrush(white)
            p.drawEllipse(c.center(), 10, 10)
        if self.hasFocus():
            p.setPen(QPen(QColor(COLORS["blue"]), 2))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(c.adjusted(-2, -2, 2, 2))
        p.end()


class VerticalMeter(QWidget):
    """Meter level vertikal per track + lampu clip yang tetap menyala sampai diklik."""

    clipReset = Signal()
    FLOOR_DB = -48.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(14)
        self._db = -120.0
        self.clip = False
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Meter level. Lampu merah di atas = clip; klik untuk mematikan.")

    def set_level(self, db: float, clip: bool = False) -> None:
        changed = abs(db - self._db) > 0.2 or (clip and not self.clip)
        self._db = db
        self.clip = self.clip or clip
        if changed:
            self.update()

    def mousePressEvent(self, event):
        if self.clip:
            self.clip = False
            self.update()
            self.clipReset.emit()

    def _y(self, db: float, top: float, height: float) -> float:
        frac = max(0.0, min(1.0, (db - self.FLOOR_DB) / -self.FLOOR_DB))
        return top + height * (1 - frac)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = float(self.width())
        lamp = QRectF(1, 0, w - 2, 8)
        lamp_color = QColor(COLORS["red"]) if self.clip else QColor(COLORS["raised"])
        p.setPen(Qt.NoPen)
        p.setBrush(lamp_color)
        p.drawRoundedRect(lamp, 2, 2)
        bar = QRectF(1, 12, w - 2, self.height() - 12)
        p.setBrush(QColor(COLORS["raised"]))
        p.drawRoundedRect(bar, 2, 2)
        inner = bar.adjusted(2, 2, -2, -2)
        for lo, hi, color in ((-120, -12, COLORS["green"]), (-12, -3, COLORS["yellow"]), (-3, 0.1, COLORS["red"])):
            if self._db <= max(lo, self.FLOOR_DB):
                continue
            y_top = self._y(min(self._db, hi, 0), inner.top(), inner.height())
            y_bottom = self._y(max(lo, self.FLOOR_DB), inner.top(), inner.height())
            p.setBrush(QColor(color))
            p.drawRect(QRectF(inner.left(), y_top, inner.width(), y_bottom - y_top))
        p.end()

    def zone(self) -> str:
        return meter_zone(self._db)


class TakeButton(QPushButton):
    """Tombol dropdown take: 'Take 2 · 13:01 ⌄'."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("takeButton")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(40)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setIconSize(QSize(16, 16))
        self.set_recording(False)

    def set_recording(self, recording: bool) -> None:
        self.setProperty("recording", recording)
        color = COLORS["red"] if recording else COLORS["text2"]
        self.setIcon(icons.icon("chevron_down", color, 16))
        refresh_style(self)


class TakePanel(QFrame):
    """Panel 'Pilih Take — <Track>' (popup) seperti mockup take_list_bass."""

    takeChosen = Signal(int)
    previewRequested = Signal(int)
    retakeRequested = Signal()

    WIDTH = 520

    def __init__(self, track: Track, playing_take: int | None, parent=None):
        super().__init__(parent, Qt.Popup)
        self.setObjectName("takePanel")
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setFixedWidth(self.WIDTH)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 12)
        lay.setSpacing(0)
        lay.addWidget(label(f"Pilih Take — {track.label}", "panelTitle"))
        lay.addSpacing(4)
        lay.addWidget(label("Take lama tidak dihapus.", "secondary"))
        lay.addSpacing(12)
        lay.addWidget(self._separator())
        lay.addSpacing(8)
        group = QButtonGroup(self)
        for take in sorted(track.takes, key=lambda t: t.id):
            row = QFrame()
            row.setObjectName("takeRow")
            row.setProperty("active", take.id == track.active_take_id)
            row.setFixedHeight(56)
            radio = QRadioButton(f"Take {take.id}")
            radio.setChecked(take.id == track.active_take_id)
            radio.setCursor(Qt.PointingHandCursor)
            group.addButton(radio)
            radio.toggled.connect(lambda on, t=take.id: on and self._choose(t))
            items = [radio]
            if not take.complete:
                badge = label("Tidak lengkap", "badgeWarn")
                badge.setFixedHeight(24)
                items += [8, badge]
            info = label(f"{take_time(take)} · {fmt_duration(take.duration)}", "mono")
            play = button("", "icon")
            playing = take.id == playing_take
            play.setIcon(icons.icon("stop" if playing else "play", COLORS["text"], 16))
            play.setToolTip("Hentikan pratinjau" if playing else "Putar pratinjau take ini")
            play.clicked.connect(lambda _=False, t=take.id: self.previewRequested.emit(t))
            row.setLayout(hbox(*items, None, info, 12, play, margins=(14, 0, 8, 0)))
            row.mousePressEvent = lambda e, r=radio: r.setChecked(True)
            lay.addWidget(row)
            lay.addSpacing(6)
        lay.addSpacing(4)
        lay.addWidget(self._separator())
        lay.addSpacing(6)
        retake = button("Rekam Ulang (Take Baru)", "danger", "mic", COLORS["red"], 18)
        retake.clicked.connect(self._retake)
        lay.addLayout(hbox(retake, None))

    @staticmethod
    def _separator() -> QFrame:
        sep = QFrame()
        sep.setObjectName("separator")
        return sep

    def _choose(self, take_id: int) -> None:
        self.takeChosen.emit(take_id)
        self.close()

    def _retake(self) -> None:
        self.close()
        self.retakeRequested.emit()


class TrackStrip(QFrame):
    """Satu bilah track: kontrol (±500 px) + waveform + meter."""

    recordClicked = Signal(str)
    soloToggled = Signal(str, bool)
    muteToggled = Signal(str, bool)
    volumeChanged = Signal(str, float)
    takeMenuRequested = Signal(str)
    selected = Signal(str)
    clipReset = Signal(str)

    def __init__(self, track_id: str, input_text: str, parent=None):
        super().__init__(parent)
        self.track_id = track_id
        self.color = TRACK_COLORS[track_id]
        self.setObjectName("trackStrip")
        self.setFixedHeight(ROW_HEIGHT)
        self.setProperty("selected", False)
        self.setProperty("recording", False)

        stripe = QFrame()
        stripe.setFixedWidth(4)
        stripe.setStyleSheet(f"background: {self.color}; border: none; border-radius: 2px;")

        dot = QWidget()
        dot.setFixedSize(10, 10)
        dot.setStyleSheet(f"background: {self.color}; border-radius: 5px;")
        self.name = label(TRACK_LABELS[track_id], "trackName")
        self.input_label = label(input_text, "secondary")
        names = vbox(None, hbox(dot, 8, self.name, None), 6, self.input_label, None)
        names_box = QWidget()
        names_box.setLayout(names)
        names_box.setFixedWidth(170)

        self.record = RecordButton()
        self.record.clicked.connect(lambda: self.recordClicked.emit(self.track_id))

        self.solo = button("S", "solo")
        self.mute = button("M", "mute")
        for b, tip in ((self.solo, "Solo: hanya track ini yang terdengar"), (self.mute, "Mute: bisukan track ini")):
            b.setCheckable(True)
            b.setFixedSize(40, 40)
            b.setToolTip(tip)
        self.solo.toggled.connect(lambda on: self.soloToggled.emit(self.track_id, on))
        self.mute.toggled.connect(lambda on: self.muteToggled.emit(self.track_id, on))

        self.volume_value = label("0.0 dB", "monoValue")
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(int(VOLUME_MIN_DB * 2), int(VOLUME_MAX_DB * 2))
        self.volume.setPageStep(2)
        self.volume.setCursor(Qt.PointingHandCursor)
        self.volume.setToolTip("Volume track (−12 s.d. +6 dB). Klik dua kali untuk kembali ke 0 dB.")
        self.volume.valueChanged.connect(self._on_volume)
        self.volume.mouseDoubleClickEvent = lambda e: self.volume.setValue(0)
        self.take_button = TakeButton()
        self.take_button.clicked.connect(lambda: self.takeMenuRequested.emit(self.track_id))
        mix = vbox(hbox(label("Volume", "secondary"), None, self.volume_value), 2, self.volume, 6,
                   self.take_button)
        mix_box = QWidget()
        mix_box.setLayout(mix)
        mix_box.setFixedWidth(170)

        controls = QWidget()
        controls.setObjectName("trackControls")
        controls.setFixedWidth(CONTROL_WIDTH)
        controls.setLayout(hbox(stripe, 12, names_box, None, self.record, 10,
                                vbox(self.solo, 8, self.mute), 12, mix_box, 14, margins=(0, 8, 0, 8)))

        self.waveform = WaveformView(self.color)
        self.meter = VerticalMeter()
        self.meter.clipReset.connect(lambda: self.clipReset.emit(self.track_id))

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 12, 0)
        lay.setSpacing(0)
        lay.addWidget(controls)
        divider = QFrame()
        divider.setFixedWidth(1)
        divider.setStyleSheet(f"background: {COLORS['border']}; border: none;")
        lay.addWidget(divider)
        lay.addSpacing(16)
        lay.addLayout(vbox(self.waveform, margins=(0, 10, 0, 10)), 1)
        lay.addSpacing(10)
        lay.addLayout(vbox(self.meter, margins=(0, 10, 0, 10)))

    # ----- tampilan dari model -----
    def show_track(self, track: Track, recording: bool = False, recording_take: int | None = None) -> None:
        self.solo.blockSignals(True)
        self.mute.blockSignals(True)
        self.volume.blockSignals(True)
        self.solo.setChecked(track.solo)
        self.mute.setChecked(track.mute)
        self.volume.setValue(int(round(track.volume_db * 2)))
        self.volume_value.setText(f"{track.volume_db:+.1f} dB".replace("+0.0", "0.0"))
        self.solo.blockSignals(False)
        self.mute.blockSignals(False)
        self.volume.blockSignals(False)
        take = track.active_take
        if recording:
            self.record.set_state(STATE_RECORDING)
            self.take_button.setText(f"Take {recording_take} · Merekam")
            self.take_button.setEnabled(True)
        elif take is not None:
            self.record.set_state(STATE_RECORDED)
            self.take_button.setText(f"Take {take.id} · {take_time(take)}")
            self.take_button.setToolTip("" if take.complete else "Take ini tidak lengkap")
            self.take_button.setProperty("incomplete", not take.complete)
            self.take_button.setEnabled(True)
        else:
            self.record.set_state(STATE_EMPTY)
            self.take_button.setProperty("incomplete", False)
            self.take_button.setText("–")
            self.take_button.setEnabled(bool(track.takes))
        self.take_button.set_recording(recording)
        self.setProperty("recording", recording)
        refresh_style(self)

    def set_input_text(self, text: str) -> None:
        self.input_label.setText(text)

    def set_selected(self, selected: bool) -> None:
        if self.property("selected") != selected:
            self.setProperty("selected", selected)
            refresh_style(self)

    def _on_volume(self, value: int) -> None:
        db = value / 2
        self.volume_value.setText(f"{db:+.1f} dB".replace("+0.0", "0.0"))
        self.volumeChanged.emit(self.track_id, db)

    def mousePressEvent(self, event):
        self.selected.emit(self.track_id)
        super().mousePressEvent(event)


__all__ = ["CONTROL_WIDTH", "RecordButton", "TakePanel", "TrackStrip", "VerticalMeter", "QSizePolicy", "QLabel",
           "QFont"]
