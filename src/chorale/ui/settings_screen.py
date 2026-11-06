"""Layar Pengaturan dua kolom (mockup: harmonisatb_studio_settings_audio_device)."""

from __future__ import annotations

import threading
from datetime import datetime

from PySide6.QtCore import QThread, QTimer, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QMessageBox, QScrollArea, QStackedWidget, QVBoxLayout,
    QWidget,
)

from chorale import __version__
from chorale.audio import device as dev
from chorale.audio.calibration import (
    SAFETY_STEPS, CalibrationCancelled, CalibrationError, CalibrationResult, accuracy_label, find_calibration,
    measure_latency, save_calibration,
)
from chorale.audio.monitor import InputMonitor
from chorale.settings import AppSettings, load_settings, save_settings
from chorale.ui import theme
from chorale.ui.theme import COLORS, TRACK_COLORS
from chorale.ui.widgets import (
    LevelMeterBar, SegmentedControl, TopBar, button, card, color_dot, hbox, icon_label, label, vbox,
)

BUFFER_LABELS = {n: f"{n} sampel" for n in dev.BLOCKSIZE_CHOICES}
INSTRUMENT_OPTIONS = [("1-2", "Input 1–2 · Stereo"), ("1", "Input 1 · Mono"), ("2", "Input 2 · Mono")]
VOCAL_OPTIONS = [("1", "Input 1 · Mono"), ("2", "Input 2 · Mono")]
LEVEL_FPS = 30


class CalibrationWorker(QThread):
    """Jalankan measure_latency di thread terpisah agar UI tetap responsif."""

    progressed = Signal(int, int, int)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, selection: dev.DeviceSelection, blocksize: int, parent=None):
        super().__init__(parent)
        self.selection = selection
        self.blocksize = blocksize
        self.cancel = threading.Event()

    def run(self) -> None:
        try:
            result = measure_latency(self.selection, self.blocksize, progress=self.progressed.emit,
                                     cancel=self.cancel)
            save_calibration(result)
            self.succeeded.emit(result)
        except CalibrationCancelled:
            self.failed.emit("Kalibrasi dibatalkan.")
        except (CalibrationError, dev.AudioDeviceError) as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"Kalibrasi gagal: {exc}")


def _combo(options: list[tuple[object, str]], compact: bool = False, mono: bool = False) -> QComboBox:
    c = QComboBox()
    if compact:
        c.setProperty("compact", True)
    if mono:
        c.setProperty("mono", True)
    for key, text in options:
        c.addItem(text, key)
    c.setCursor(Qt.PointingHandCursor)
    return c


def _select_data(combo: QComboBox, value) -> None:
    i = combo.findData(value)
    if i >= 0:
        combo.setCurrentIndex(i)


class LockedField(QFrame):
    """Kotak nilai terkunci, mis. 'Sample Rate  48.000 Hz 🔒'."""

    def __init__(self, name: str, value: str, parent=None):
        super().__init__(parent)
        self.setObjectName("lockedField")
        self.setFixedHeight(40)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.addWidget(label(name, "secondary"))
        lay.addStretch(1)
        lay.addWidget(label(value, "monoValue"))
        lay.addSpacing(8)
        lay.addWidget(icon_label("lock", COLORS["text2"], 16))
        self.setToolTip("Dikunci agar semua rekaman 48 kHz / 24-bit.")


class AudioDevicePage(QWidget):
    """Isi halaman 'Perangkat Audio'."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("scrollContent")
        self._cards: list[dev.SoundCard] = []
        self._selection: dev.DeviceSelection | None = None
        self._monitor: InputMonitor | None = None
        self._worker: CalibrationWorker | None = None
        self._mode_touched = False
        self.settings = AppSettings()

        # Sound Card
        self.device_combo = QComboBox()
        self.device_combo.setCursor(Qt.PointingHandCursor)
        self.mode = SegmentedControl(
            [(dev.MODE_ASIO, "ASIO"), (dev.MODE_EXCLUSIVE, "WASAPI Exclusive"), (dev.MODE_SHARED, "WASAPI Shared")],
            height=54, background="rgba(14, 17, 22, 0.6)")
        self.buffer_combo = _combo(list(BUFFER_LABELS.items()), mono=True)
        self.device_status = label("", "error")
        self.device_status.setWordWrap(True)
        self.device_status.hide()
        locked = QGridLayout()
        locked.setHorizontalSpacing(16)
        locked.addWidget(LockedField("Sample Rate", "48.000 Hz"), 0, 0)
        locked.addWidget(LockedField("Bit Depth", "24-bit"), 0, 1)
        sound = card()
        sound.setLayout(vbox(
            label("Sound Card", "h3"), 12,
            label("Perangkat", "field"), 6, self.device_combo, 12,
            label("Mode Driver", "field"), 6, self.mode, 4, self.device_status, 6,
            locked, 12,
            label("Ukuran Buffer", "field"), 6, self.buffer_combo, 6,
            label("Naikkan jika terdengar putus-putus.", "hint"),
            margins=(24, 20, 24, 20)))

        # Pemetaan Input
        self.instrument_combo = _combo(INSTRUMENT_OPTIONS, compact=True)
        self.vocal_combo = _combo(VOCAL_OPTIONS, compact=True)
        self.instrument_meter = LevelMeterBar(180)
        self.vocal_meter = LevelMeterBar(180)
        self.meter_status = label("", "hint")
        self.meter_status.setWordWrap(True)
        sep = QFrame()
        sep.setObjectName("separator")
        mapping = card()
        mapping.setLayout(vbox(
            label("Pemetaan Input", "h3"), 12,
            hbox(color_dot(TRACK_COLORS["piano"]), 8, label("Instrumen (Piano/Orgen)", "body"), None,
                 self.instrument_meter), 8,
            self.instrument_combo, 12, sep, 12,
            hbox(color_dot(COLORS["blue"]), 8, label("Vokal (Mikrofon)", "body"), None, self.vocal_meter), 8,
            self.vocal_combo, 6, self.meter_status, None,
            margins=(24, 20, 24, 20)))

        # Kalibrasi Latensi
        intro = label("Hubungkan kabel dari Output ke Input sound card, lalu tekan Mulai Kalibrasi. "
                      "Cukup dilakukan sekali.", "secondary")
        intro.setWordWrap(True)
        intro.setStyleSheet("font-size: 14px; line-height: 150%;")
        self.latency_value = label("—")
        self.latency_value.setFont(theme.font(18, QFont.DemiBold, mono=True))
        self.accuracy_badge = label("")
        self.last_calibrated = label("", "hintMono")
        result_box = card("inset")
        result_box.setLayout(vbox(
            hbox(label("Latensi terukur", "secondary"), None, self.latency_value, 10, self.accuracy_badge), 8,
            self.last_calibrated, margins=(16, 12, 16, 12)))
        self.calibrate_btn = button("Mulai Kalibrasi", "primary", "timer", "#FFFFFF", 20)
        self.calibrate_btn.clicked.connect(self.start_calibration)
        self.calibration_msg = label("", "error")
        self.calibration_msg.setWordWrap(True)
        self.calibration_msg.hide()
        calib = card()
        calib.setLayout(vbox(label("Kalibrasi Latensi", "h3"), 8, intro, 12, result_box, 14,
                             hbox(self.calibrate_btn, None), 6, self.calibration_msg, None,
                             margins=(24, 20, 24, 20)))

        row = QGridLayout()
        row.setHorizontalSpacing(16)
        row.addWidget(mapping, 0, 0)
        row.addWidget(calib, 0, 1)
        row.setColumnStretch(0, 1)
        row.setColumnStretch(1, 1)

        self.cancel_btn = button("Batal", "secondary")
        self.save_btn = button("Simpan", "primary")
        self.cancel_btn.setMinimumWidth(110)
        self.save_btn.setMinimumWidth(150)

        content = QWidget()
        content.setObjectName("scrollContent")
        content.setMaximumWidth(880)
        content.setLayout(vbox(label("Perangkat Audio", "h2"), 12, sound, 14, row, 16,
                               hbox(None, self.cancel_btn, 16, self.save_btn)))
        self.setLayout(hbox(content, None, margins=(48, 18, 48, 18)))

        self.device_combo.currentIndexChanged.connect(self._on_device_changed)
        self.mode.changed.connect(self._on_mode_changed)
        self.buffer_combo.currentIndexChanged.connect(lambda _i: self._reselect())
        self._meter_timer = QTimer(self)
        self._meter_timer.setInterval(1000 // LEVEL_FPS)
        self._meter_timer.timeout.connect(self._update_meters)

    # ----- muat & simpan -----
    def load(self, settings: AppSettings, cards: list[dev.SoundCard] | None = None) -> None:
        self.settings = settings
        self._mode_touched = False
        self._cards = dev.list_sound_cards() if cards is None else cards
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        for c in self._cards:
            self.device_combo.addItem(c.name, c.name)
        if settings.device_name and self.device_combo.findData(settings.device_name) < 0:
            self.device_combo.addItem(f"{settings.device_name} (tidak tersambung)", settings.device_name)
        if self.device_combo.count() == 0:
            self.device_combo.addItem("Tidak ada sound card yang terdeteksi", None)
            self.device_combo.setEnabled(False)
        else:
            self.device_combo.setEnabled(True)
        wanted = settings.device_name or next(
            (c.name for c in self._cards if dev.matches_keyword(c.name)), None)
        if wanted is not None:
            _select_data(self.device_combo, wanted)
        self.device_combo.blockSignals(False)
        _select_data(self.buffer_combo, settings.blocksize)
        _select_data(self.instrument_combo, settings.instrument_input)
        _select_data(self.vocal_combo, settings.vocal_input)
        self._on_device_changed()

    def collect(self) -> AppSettings:
        """Pengaturan dari isian layar (belum disimpan)."""
        s = AppSettings(**vars(self.settings))
        s.device_name = self.device_combo.currentData()
        s.driver_mode = self.mode.value() if self._mode_touched else self.settings.driver_mode
        s.blocksize = self.buffer_combo.currentData()
        s.instrument_input = self.instrument_combo.currentData()
        s.vocal_input = self.vocal_combo.currentData()
        return s

    # ----- perangkat -----
    def _current_card(self) -> dev.SoundCard | None:
        name = self.device_combo.currentData()
        return next((c for c in self._cards if c.name == name), None)

    def _on_device_changed(self, _index: int = 0) -> None:
        sound_card = self._current_card()
        modes = sound_card.modes if sound_card else ()
        for m in (dev.MODE_ASIO, dev.MODE_EXCLUSIVE, dev.MODE_SHARED):
            available = m in modes
            self.mode.set_option_enabled(m, available, "" if available or m != dev.MODE_ASIO else "Tidak tersedia")
        preferred = self.settings.driver_mode if self.settings.driver_mode in modes else None
        if preferred is None and modes:
            preferred = modes[0]
        if preferred:
            self.mode.set_value(preferred)
        self._reselect()

    def _on_mode_changed(self, _mode) -> None:
        self._mode_touched = True
        self._reselect()

    def _reselect(self) -> None:
        """Pilih ulang perangkat sesuai isian, lalu mulai ulang meter dan tampilkan kalibrasi."""
        self.stop_monitor()
        self._selection = None
        sound_card = self._current_card()
        self.device_status.hide()
        if sound_card is not None and self.mode.value() in sound_card.modes:
            try:
                self._selection = dev.select_device(sound_card.name, mode=self.mode.value())
            except dev.AudioDeviceError as exc:
                self.device_status.setText(str(exc))
                self.device_status.show()
        elif self.device_combo.isEnabled():
            self.device_status.setText(dev.MSG_NOT_FOUND)
            self.device_status.show()
        self.calibrate_btn.setEnabled(self._selection is not None)
        self._show_calibration()
        if self.isVisible():
            self.start_monitor()

    # ----- meter -----
    def start_monitor(self) -> None:
        if self._selection is None or self._worker is not None:
            self.meter_status.setText("Meter aktif setelah sound card dipilih." if self._selection is None else "")
            return
        try:
            self._monitor = InputMonitor(self._selection, self.buffer_combo.currentData())
            self._monitor.start()
            self.meter_status.setText("")
            self._meter_timer.start()
        except dev.AudioDeviceError as exc:
            self._monitor = None
            self.meter_status.setText(f"Meter tidak aktif: {exc}")

    def stop_monitor(self) -> None:
        self._meter_timer.stop()
        if self._monitor is not None:
            self._monitor.stop()
            self._monitor = None
        self.instrument_meter.set_db(-120)
        self.vocal_meter.set_db(-120)

    def _update_meters(self) -> None:
        if self._monitor is None:
            return
        peaks = self._monitor.peaks_db()
        first, count = AppSettings(instrument_input=self.instrument_combo.currentData()).instrument_channels()
        inst = peaks[first:first + count]
        self.instrument_meter.set_db(float(inst.max()) if len(inst) else -120.0)
        vocal = int(self.vocal_combo.currentData()) - 1
        self.vocal_meter.set_db(float(peaks[vocal]) if vocal < len(peaks) else -120.0)

    def showEvent(self, event):
        super().showEvent(event)
        self.start_monitor()

    def hideEvent(self, event):
        self.stop_monitor()
        super().hideEvent(event)

    # ----- kalibrasi -----
    def _show_calibration(self, result: CalibrationResult | None = None) -> None:
        if result is None and self._selection is not None:
            s = self._selection
            result = find_calibration(s.input.name, s.output.name, s.hostapi, s.exclusive,
                                      self.buffer_combo.currentData())
        if result is None:
            self.latency_value.setText("—")
            self.accuracy_badge.setText("Belum dikalibrasi")
            self._badge_style(COLORS["text2"], "rgba(139, 152, 165, 0.12)")
            self.last_calibrated.setText("Belum pernah dikalibrasi untuk pengaturan ini")
            return
        text, level = accuracy_label(result)
        color = {"baik": COLORS["green"], "cukup": COLORS["yellow"], "buruk": COLORS["red"]}[level]
        bg = {"baik": "rgba(34, 197, 94, 0.12)", "cukup": "rgba(234, 179, 8, 0.12)",
              "buruk": "rgba(239, 68, 68, 0.12)"}[level]
        self.latency_value.setText(f"{result.latency_ms:.1f} ms")
        self.accuracy_badge.setText(("✓ " if level == "baik" else "") + text)
        self._badge_style(color, bg)
        try:
            when = datetime.fromisoformat(result.date).strftime("%d-%m-%Y %H:%M")
        except ValueError:
            when = result.date
        self.last_calibrated.setText(f"Terakhir dikalibrasi {when}")

    def _badge_style(self, color: str, bg: str) -> None:
        self.accuracy_badge.setStyleSheet(
            f"color: {color}; background: {bg}; border-radius: 4px; padding: 3px 8px; font-size: 14px; "
            "font-weight: 500;")

    def start_calibration(self) -> None:
        if self._selection is None or self._worker is not None:
            return
        steps = "\n".join(f"{i}. {s}" for i, s in enumerate(SAFETY_STEPS, 1))
        box = QMessageBox(QMessageBox.Information, "Mulai Kalibrasi",
                          f"Sebelum mulai, demi keamanan telinga dan peralatan:\n\n{steps}\n\n"
                          "Aplikasi akan memutar bunyi pendek 5 kali.", parent=self)
        start = box.addButton("Mulai", QMessageBox.AcceptRole)
        box.addButton("Batal", QMessageBox.RejectRole)
        box.setDefaultButton(start)
        box.exec()
        if box.clickedButton() is not start:
            return
        self.stop_monitor()
        self.calibration_msg.hide()
        self.calibrate_btn.setEnabled(False)
        self.calibrate_btn.setText("Mengukur…")
        self._worker = CalibrationWorker(self._selection, self.buffer_combo.currentData(), self)
        self._worker.progressed.connect(
            lambda run, runs, _lag: self.calibrate_btn.setText(f"Mengukur… {run}/{runs}"))
        self._worker.succeeded.connect(self._calibration_done)
        self._worker.failed.connect(self._calibration_failed)
        self._worker.finished.connect(self._calibration_finished)
        self._worker.start()

    def _calibration_done(self, result: CalibrationResult) -> None:
        self._show_calibration(result)

    def _calibration_failed(self, message: str) -> None:
        self.calibration_msg.setText(message)
        self.calibration_msg.show()

    def _calibration_finished(self) -> None:
        self._worker.deleteLater()
        self._worker = None
        self.calibrate_btn.setText("Mulai Kalibrasi")
        self.calibrate_btn.setEnabled(self._selection is not None)
        if self.isVisible():
            self.start_monitor()

    def shutdown(self) -> None:
        """Hentikan meter & kalibrasi (saat jendela ditutup)."""
        self.stop_monitor()
        if self._worker is not None:
            self._worker.cancel.set()
            self._worker.wait(10000)


class AboutPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("scrollContent")
        lines = [
            ("HarmoniSATB Studio", "h3"),
            (f"Versi {__version__}", "mono"),
            ("Aplikasi untuk merekam paduan suara SATB dan piano secara bergiliran, lalu membuat master "
             "siap YouTube dengan satu klik.", "secondary"),
            ("Komponen pihak ketiga", "field"),
            ("Qt for Python (PySide6) · LGPL v3", "secondary"),
            ("PortAudio, libsndfile, FFmpeg · lisensi masing-masing", "secondary"),
            ("Font Inter dan JetBrains Mono · SIL Open Font License 1.1", "secondary"),
        ]
        content = QWidget()
        content.setObjectName("scrollContent")
        content.setFixedWidth(880)
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        lay.addWidget(label("Tentang Aplikasi", "h2"))
        lay.addSpacing(8)
        box = card()
        inner = QVBoxLayout(box)
        inner.setContentsMargins(24, 22, 24, 22)
        inner.setSpacing(8)
        for text, role in lines:
            w = label(text, role)
            w.setWordWrap(True)
            if role == "field":
                inner.addSpacing(12)
            inner.addWidget(w)
        lay.addWidget(box)
        lay.addStretch(1)
        self.setLayout(hbox(content, None, margins=(48, 24, 48, 24)))


class SettingsScreen(QWidget):
    """Bilah atas + navigasi samping + halaman."""

    closed = Signal()
    saved = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("screen")
        bar = TopBar()
        bar.layout_.setSpacing(16)
        back = button("", "square", "arrow_left", COLORS["text2"], 20)
        back.setToolTip("Kembali")
        back.clicked.connect(self.cancel)
        bar.layout_.addWidget(back)
        bar.layout_.addWidget(label("Pengaturan", "appTitle"))
        bar.layout_.addStretch(1)

        nav = QFrame()
        nav.setObjectName("sideNav")
        nav.setFixedWidth(240)
        self.nav_audio = button("Perangkat Audio", "nav")
        self.nav_about = button("Tentang Aplikasi", "nav")
        for b in (self.nav_audio, self.nav_about):
            b.setCheckable(True)
            b.setAutoExclusive(True)
        self.nav_audio.setChecked(True)
        nav.setLayout(vbox(self.nav_audio, self.nav_about, None, margins=(0, 12, 0, 0)))

        self.audio_page = AudioDevicePage()
        self.about_page = AboutPage()
        self.pages = QStackedWidget()
        for page in (self.audio_page, self.about_page):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(page)
            self.pages.addWidget(scroll)
        self.nav_audio.clicked.connect(lambda: self.pages.setCurrentIndex(0))
        self.nav_about.clicked.connect(lambda: self.pages.setCurrentIndex(1))

        self.audio_page.cancel_btn.clicked.connect(self.cancel)
        self.audio_page.save_btn.clicked.connect(self.save)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(bar)
        body = QHBoxLayout()
        body.setSpacing(0)
        body.addWidget(nav)
        body.addWidget(self.pages, 1)
        root.addLayout(body, 1)

    def open(self, settings: AppSettings | None = None, cards=None) -> None:
        self.nav_audio.setChecked(True)
        self.pages.setCurrentIndex(0)
        self.audio_page.load(settings or load_settings(), cards)

    def save(self) -> None:
        settings = self.audio_page.collect()
        save_settings(settings)
        self.audio_page.settings = settings
        self.saved.emit(settings)
        self.closed.emit()

    def cancel(self) -> None:
        self.closed.emit()

    def shutdown(self) -> None:
        self.audio_page.shutdown()
