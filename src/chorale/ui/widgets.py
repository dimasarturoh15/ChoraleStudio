"""Widget kecil yang dipakai ulang di semua layar."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QIntValidator, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton, QButtonGroup, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy,
    QVBoxLayout, QWidget,
)

from chorale.audio.meter import meter_zone
from chorale.ui import icons, theme
from chorale.ui.theme import COLORS


def label(text: str, role: str | None = None, parent: QWidget | None = None) -> QLabel:
    w = QLabel(text, parent)
    if role:
        w.setProperty("role", role)
    return w


def button(text: str, variant: str = "secondary", icon_name: str | None = None,
           icon_color: str = "#FFFFFF", icon_size: int = 20) -> QPushButton:
    # Qt tidak punya jarak ikon-teks di QSS; dua spasi memberi jarak ~8 px seperti mockup.
    b = QPushButton(f"  {text}" if icon_name and text else text)
    b.setProperty("variant", variant)
    b.setCursor(Qt.PointingHandCursor)
    if icon_name:
        b.setIcon(icons.icon(icon_name, icon_color, icon_size))
        b.setIconSize(QSize(icon_size, icon_size))
    return b


def card(object_name: str = "card") -> QFrame:
    f = QFrame()
    f.setObjectName(object_name)
    return f


def icon_label(name: str, color: str, size: int) -> QLabel:
    w = QLabel()
    w.setPixmap(icons.pixmap(name, color, size))
    w.setFixedSize(size, size)
    return w


def refresh_style(w: QWidget) -> None:
    """Terapkan ulang QSS setelah properti dinamis berubah."""
    w.style().unpolish(w)
    w.style().polish(w)
    w.update()


class SegmentButton(QAbstractButton):
    """Satu pilihan pada SegmentedControl; bisa punya teks kecil di bawahnya (mis. 'Tidak tersedia')."""

    def __init__(self, text: str, sublabel: str = "", mono: bool = False, parent=None):
        super().__init__(parent)
        self.setText(text)
        self.sublabel = sublabel
        self.mono = mono
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._hover = False

    def sizeHint(self) -> QSize:
        fm = self.fontMetrics()
        return QSize(fm.horizontalAdvance(self.text()) + 24, 36)

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        if self.isChecked():
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(COLORS["blue"]))
            p.drawRoundedRect(r, 6, 6)
            color = QColor("#FFFFFF")
        elif not self.isEnabled():
            color = QColor(COLORS["text2"])
            color.setAlphaF(0.45)
        else:
            if self._hover:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(COLORS["raised"]))
                p.drawRoundedRect(r, 6, 6)
            color = QColor(COLORS["text"] if self._hover else COLORS["text2"])
        weight = QFont.DemiBold if self.isChecked() else QFont.Medium
        p.setPen(color)
        if self.sublabel:
            main_font, sub_font = theme.font(14, QFont.Medium, self.mono), theme.font(13)
            h1 = QFontMetricsF(main_font).height()
            h2 = QFontMetricsF(sub_font).height()
            y = r.y() + (r.height() - h1 - h2) / 2
            p.setFont(main_font)
            p.drawText(QRectF(r.x(), y, r.width(), h1), Qt.AlignCenter, self.text())
            p.setFont(sub_font)
            p.drawText(QRectF(r.x(), y + h1, r.width(), h2), Qt.AlignCenter, self.sublabel)
        else:
            p.setFont(theme.font(14, weight, self.mono))
            p.drawText(r, Qt.AlignCenter, self.text())
        p.end()


class SegmentedControl(QFrame):
    """Pilihan tunggal berbentuk deretan tombol (Birama, Hitungan Awal, Mode Driver)."""

    changed = Signal(object)

    def __init__(self, options: list[tuple[object, str]], mono: bool = False, height: int = 48,
                 sublabels: dict | None = None, background: str | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("segmented")
        bg = background or COLORS["raised"]
        self.setStyleSheet(f"QFrame#segmented {{ background: {bg}; border: 1px solid {COLORS['border']}; "
                           "border-radius: 8px; }")
        self.setFixedHeight(height)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[object, SegmentButton] = {}
        for key, text in options:
            b = SegmentButton(text, (sublabels or {}).get(key, ""), mono)
            self._group.addButton(b)
            self._buttons[key] = b
            lay.addWidget(b)
            b.clicked.connect(lambda _=False, k=key: self.changed.emit(k))

    def value(self):
        for key, b in self._buttons.items():
            if b.isChecked():
                return key
        return None

    def set_value(self, key) -> None:
        if key in self._buttons:
            self._buttons[key].setChecked(True)

    def set_option_enabled(self, key, enabled: bool, sublabel: str | None = None) -> None:
        b = self._buttons[key]
        b.setEnabled(enabled)
        b.setCursor(Qt.PointingHandCursor if enabled else Qt.ForbiddenCursor)
        if sublabel is not None:
            b.sublabel = sublabel
        b.update()

    def button(self, key) -> SegmentButton:
        return self._buttons[key]


class ToggleSwitch(QAbstractButton):
    """Sakelar geser 48x26 px seperti mockup."""

    def __init__(self, checked: bool = True, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(48, 26)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(COLORS["blue"] if self.isChecked() else COLORS["gray"]))
        p.drawRoundedRect(QRectF(self.rect()), 13, 13)
        p.setBrush(QColor("#FFFFFF"))
        x = self.width() - 23 if self.isChecked() else 3
        p.drawEllipse(QRectF(x, 3, 20, 20))
        p.end()


class Stepper(QFrame):
    """Isian angka dengan tombol − dan + (Tempo). Nilai di luar batas dikembalikan ke batas terdekat."""

    valueChanged = Signal(int)

    def __init__(self, value: int, minimum: int, maximum: int, parent=None):
        super().__init__(parent)
        self.setObjectName("inset")
        self.setFixedHeight(48)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 8, 0)
        self.minimum, self.maximum = minimum, maximum
        self.minus = button("–", "step")
        self.plus = button("+", "step")
        self.edit = QLineEdit(str(value))
        self.edit.setObjectName("stepperEdit")
        self.edit.setAlignment(Qt.AlignCenter)
        self.edit.setValidator(QIntValidator(0, 999, self.edit))
        self.edit.setMaxLength(3)
        lay.addWidget(self.minus)
        lay.addWidget(self.edit, 1)
        lay.addWidget(self.plus)
        self.minus.clicked.connect(lambda: self.step(-1))
        self.plus.clicked.connect(lambda: self.step(1))
        self.minus.setAutoRepeat(True)
        self.plus.setAutoRepeat(True)
        self.edit.editingFinished.connect(lambda: self.set_value(self.value()))

    def raw_value(self) -> int | None:
        try:
            return int(self.edit.text())
        except ValueError:
            return None

    def value(self) -> int:
        """Nilai yang sudah dibatasi ke rentang yang diizinkan."""
        raw = self.raw_value()
        return self.minimum if raw is None else max(self.minimum, min(self.maximum, raw))

    def set_value(self, value: int) -> None:
        value = max(self.minimum, min(self.maximum, int(value)))
        if self.edit.text() != str(value):
            self.edit.setText(str(value))
        self.valueChanged.emit(value)

    def step(self, delta: int) -> None:
        self.set_value(self.value() + delta)


class StatusDots(QWidget):
    """Lima titik status track: hijau = terekam, abu = kosong."""

    SIZE, GAP = 12, 8

    def __init__(self, states: list[bool], parent=None):
        super().__init__(parent)
        self.states = states
        self.setFixedSize(5 * self.SIZE + 4 * self.GAP, self.SIZE)
        names = ("Piano/Orgen", "Bass", "Tenor", "Alto", "Sopran")
        self.setToolTip(", ".join(f"{n}: {'terekam' if s else 'kosong'}" for n, s in zip(names, states)))

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        for i, done in enumerate(self.states):
            p.setBrush(QColor(COLORS["green"] if done else COLORS["gray"]))
            p.drawEllipse(QRectF(i * (self.SIZE + self.GAP), 0, self.SIZE, self.SIZE))
        p.end()


class LevelMeterBar(QWidget):
    """Meter level horizontal dengan skala -42 / -12 / 0 dB (zona warna FR-1)."""

    FLOOR_DB = -48.0

    def __init__(self, width: int = 150, parent=None):
        super().__init__(parent)
        self.setFixedSize(width, 32)
        self._db = -120.0

    def set_db(self, db: float) -> None:
        self._db = float(db)
        self.update()

    def _x(self, db: float, w: float) -> float:
        return max(0.0, min(1.0, (db - self.FLOOR_DB) / -self.FLOOR_DB)) * w

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = float(self.width())
        p.setFont(theme.font(13, mono=True))
        p.setPen(QColor(COLORS["text2"]))
        fm = p.fontMetrics()
        # Label ditaruh dari kanan ke kiri; jika bertabrakan, label kiri digeser agar tidak menimpa.
        limit = w
        for text, db, color in (("0 dB", 0, COLORS["red"]), ("-12", -12, COLORS["text2"]),
                                ("-42", -42, COLORS["text2"])):
            tw = fm.horizontalAdvance(text)
            x = min(limit - tw, max(0.0, self._x(db, w) - (tw if db == 0 else tw / 2)))
            p.setPen(QColor(color))
            p.drawText(QRectF(x, 0, tw + 1, 18), Qt.AlignLeft | Qt.AlignVCenter, text)
            limit = x - 6
        bar = QRectF(0, 21, w, 10)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(COLORS["raised"]))
        p.drawRoundedRect(bar, 2, 2)
        inner = bar.adjusted(2, 2, -2, -2)
        segments = ((-120, -12, COLORS["green"]), (-12, -3, COLORS["yellow"]), (-3, 0.1, COLORS["red"]))
        for lo, hi, color in segments:
            x0 = inner.x() + self._x(max(lo, self.FLOOR_DB), inner.width())
            x1 = inner.x() + self._x(min(hi, 0), inner.width())
            lit = inner.x() + self._x(self._db, inner.width())
            off = QColor(COLORS["gray"])
            off.setAlphaF(0.4)
            p.setBrush(off)
            p.drawRoundedRect(QRectF(x0, inner.y(), x1 - x0 - 1, inner.height()), 1, 1)
            if self._db > max(lo, self.FLOOR_DB):
                p.setBrush(QColor(color))
                p.drawRoundedRect(QRectF(x0, inner.y(), min(lit, x1) - x0 - 1, inner.height()), 1, 1)
        p.end()

    def zone(self) -> str:
        return meter_zone(self._db)


class TopBar(QFrame):
    """Bilah atas 56 px."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("topBar")
        self.setFixedHeight(56)
        self.layout_ = QHBoxLayout(self)
        self.layout_.setContentsMargins(24, 0, 24, 0)
        self.layout_.setSpacing(12)


def vbox(*widgets, spacing: int = 0, margins=(0, 0, 0, 0)) -> QVBoxLayout:
    lay = QVBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    for w in widgets:
        if isinstance(w, int):
            lay.addSpacing(w)
        elif w is None:
            lay.addStretch(1)
        elif isinstance(w, QWidget):
            lay.addWidget(w)
        else:
            lay.addLayout(w)
    return lay


def hbox(*widgets, spacing: int = 0, margins=(0, 0, 0, 0)) -> QHBoxLayout:
    lay = QHBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    for w in widgets:
        if isinstance(w, int):
            lay.addSpacing(w)
        elif w is None:
            lay.addStretch(1)
        elif isinstance(w, QWidget):
            lay.addWidget(w)
        else:
            lay.addLayout(w)
    return lay


def color_dot(color: str, size: int = 10) -> QWidget:
    w = QWidget()
    w.setFixedSize(size, size)
    w.setStyleSheet(f"background: {color}; border-radius: {size // 2}px;")
    return w


__all__ = [
    "LevelMeterBar", "SegmentedControl", "Stepper", "StatusDots", "ToggleSwitch", "TopBar", "button",
    "card", "color_dot", "hbox", "icon_label", "label", "refresh_style", "vbox", "QPen",
]
