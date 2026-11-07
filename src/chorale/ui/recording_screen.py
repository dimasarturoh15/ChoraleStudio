"""Layar Utama Perekaman (mockup: main_recording_screen, recording_state, take_list_bass)."""

from __future__ import annotations

import math

from PySide6.QtCore import QPoint, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractButton, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QMessageBox, QPushButton, QScrollArea, QSlider,
    QVBoxLayout, QWidget,
)

from chorale.audio.meter import to_dbfs
from chorale.audio.player import audible_tracks, TrackAudio, db_to_gain
from chorale.dsp.presets import REVERB_AMOUNT_LABELS, ROOM_PRESETS
from chorale.project.model import TRACK_IDS, VOCAL_TRACK_IDS, Project
from chorale.settings import AppSettings, save_settings
from chorale.ui import icons
from chorale.ui.audio_controller import IDLE, PLAYING, PREPARING, PREVIEW, RECORDING, AudioController
from chorale.ui.device_error import DeviceErrorOverlay
from chorale.ui.theme import COLORS
from chorale.ui.track_strip import TakePanel, TrackStrip
from chorale.ui.vocal_guide import VocalGuideOverlay
from chorale.ui.waveform import PeakCache, peak_at, view_seconds_for
from chorale.ui.widgets import SegmentedControl, TopBar, button, hbox, label, refresh_style, vbox

FPS = 30
MSG_NEED_ALL = "Rekam kelima track terlebih dahulu"
MSG_WARMING_UP = "Menyiapkan sound card …"


def fmt_clock(seconds: float) -> str:
    sign = "-" if seconds < 0 else ""
    seconds = abs(seconds)
    m, s = divmod(seconds, 60)
    return f"{sign}{int(m):02d}:{s:06.3f}"


def input_text(track_id: str, settings: AppSettings) -> str:
    if track_id == "piano":
        if settings.instrument_input == "1-2":
            return "Input 1–2 · Stereo"
        return f"Input {settings.instrument_input} · Mono"
    return f"Input {settings.vocal_input} · Mic"


class InfoBox(QFrame):
    """Kotak kecil 'Tempo / 72 BPM'."""

    def __init__(self, title: str, width: int, parent=None):
        super().__init__(parent)
        self.setObjectName("infoBox")
        self.setFixedSize(width, 60)
        self.value = label("", "infoValue")
        self.value.setAlignment(Qt.AlignCenter)
        t = label(title, "infoTitle")
        t.setAlignment(Qt.AlignCenter)
        self.setLayout(vbox(t, 2, self.value, margins=(8, 6, 8, 6)))


class Toast(QLabel):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("toast")
        self.setWordWrap(True)
        self.setMaximumWidth(760)
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_message(self, text: str, error: bool = False, ms: int = 5000) -> None:
        self.setProperty("error", error)
        refresh_style(self)
        self.setText(text)
        self.adjustSize()
        parent = self.parentWidget()
        self.move((parent.width() - self.width()) // 2, parent.height() - self.height() - 112)
        self.show()
        self.raise_()
        self._timer.start(ms)


class RecordingScreen(QWidget):
    controller_factory = AudioController  # bisa diganti di tes

    backRequested = Signal()
    settingsRequested = Signal()
    produceRequested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("screen")
        self.project: Project | None = None
        self.settings = AppSettings()
        self.controller: AudioController | None = None
        self.peaks = PeakCache(self)
        self.peaks.ready.connect(self._peaks_ready)
        self.selected_track = "piano"
        self._dimmed: list[QWidget] = []
        self._blink = 0
        self._last_mode = IDLE
        self._take_panel: TakePanel | None = None

        # ----- bar atas -----
        bar = TopBar()
        bar.layout_.setSpacing(16)
        back = button("", "square", "arrow_left", COLORS["text2"], 20)
        back.setToolTip("Kembali ke daftar proyek")
        back.clicked.connect(self._go_back)
        self.title = label("", "appTitle")
        self.status_pill = QPushButton()
        self.status_pill.setObjectName("statusPill")
        self.status_pill.setCursor(Qt.PointingHandCursor)
        self.status_pill.clicked.connect(self._pill_clicked)
        settings_btn = button("Pengaturan", "toolbar", "gear", COLORS["text2"], 16)
        settings_btn.clicked.connect(self._open_settings)
        bar.layout_.addWidget(back)
        bar.layout_.addWidget(self.title)
        bar.layout_.addStretch(1)
        bar.layout_.addWidget(self.status_pill)
        bar.layout_.addStretch(1)
        bar.layout_.addWidget(settings_btn)
        self._back_btn, self._settings_btn = back, settings_btn

        # ----- transport -----
        self.to_start = self._round_button("skip_back", "Ke Awal", "transport")
        self.play_btn = self._round_button("play", "Putar (Spasi)", "transportPlay")
        self.stop_btn = self._round_button("stop", "Stop (Spasi)", "transport")
        self.to_start.clicked.connect(self._to_start)
        self.play_btn.clicked.connect(self.play)
        self.stop_btn.clicked.connect(self.stop)
        self.clock = label("00:00.000", "clock")
        self.clock.setAlignment(Qt.AlignCenter)
        clock_box = QFrame()
        clock_box.setObjectName("clockBox")
        clock_box.setFixedSize(270, 60)
        clock_box.setLayout(vbox(self.clock, margins=(16, 0, 16, 0)))
        self.tempo_box = InfoBox("Tempo", 104)
        self.ts_box = InfoBox("Birama", 92)
        self.count_box = InfoBox("Hitungan Awal", 128)
        self.metronome_btn = button("Metronom", "metronome", "metronome", COLORS["blue"], 20)
        self.metronome_btn.setCheckable(True)
        self.metronome_btn.toggled.connect(self._metronome_toggled)
        self.metro_value = label("80%", "monoValue")
        self.metro_slider = QSlider(Qt.Horizontal)
        self.metro_slider.setRange(0, 100)
        self.metro_slider.setFixedWidth(150)
        self.metro_slider.valueChanged.connect(lambda v: self.metro_value.setText(f"{v}%"))
        self.metro_slider.sliderReleased.connect(self._metronome_volume_changed)
        metro_vol = vbox(hbox(label("Volume Metronom", "secondary"), None, self.metro_value), 6, self.metro_slider)
        transport = QFrame()
        transport.setObjectName("transportBar")
        transport.setFixedHeight(84)
        transport.setLayout(hbox(self.to_start, 12, self.play_btn, 12, self.stop_btn, 20, clock_box, None,
                                 self.tempo_box, 12, self.ts_box, 12, self.count_box, None,
                                 self.metronome_btn, 20, metro_vol, margins=(24, 0, 24, 0)))
        self._transport_info = [self.tempo_box, self.ts_box, self.count_box]

        # ----- banner merekam -----
        self.banner = QFrame()
        self.banner.setObjectName("recBanner")
        self.banner.setFixedHeight(40)
        self.banner_text = label("", "recBannerText")
        self.banner_hint = label("Tekan Stop untuk selesai", "recBannerHint")
        self.banner.setLayout(hbox(self.banner_text, None, self.banner_hint, margins=(24, 0, 24, 0)))
        self.banner.hide()

        # ----- track -----
        self.strips: dict[str, TrackStrip] = {}
        tracks_box = QWidget()
        tracks_box.setObjectName("scrollContent")
        tracks_lay = QVBoxLayout(tracks_box)
        tracks_lay.setContentsMargins(24, 14, 24, 14)
        tracks_lay.setSpacing(8)
        for tid in TRACK_IDS:
            strip = TrackStrip(tid, "")
            strip.recordClicked.connect(self.record)
            strip.soloToggled.connect(self._solo)
            strip.muteToggled.connect(self._mute)
            strip.volumeChanged.connect(self._volume)
            strip.takeMenuRequested.connect(self._open_takes)
            strip.selected.connect(self.select_track)
            strip.clipReset.connect(self._clip_reset)
            self.strips[tid] = strip
            tracks_lay.addWidget(strip)
        tracks_lay.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(tracks_box)

        # ----- bar produksi -----
        self.room = SegmentedControl([(k, v.label) for k, v in ROOM_PRESETS.items()], height=46)
        self.room.changed.connect(lambda key: self._update_project(room_preset=key))
        self.amount = SegmentedControl(list(REVERB_AMOUNT_LABELS.items()), height=46)
        self.amount.changed.connect(lambda key: self._update_project(reverb_amount=key))
        self.room.setFixedWidth(400)
        self.amount.setFixedWidth(340)
        # "&&" = tanda & sungguhan (satu "&" dianggap Qt sebagai penanda shortcut).
        self.produce_btn = button("Proses Produksi && Master", "produce", "sparkles", "#FFFFFF", 22)
        self.produce_btn.clicked.connect(lambda: self.produceRequested.emit(self.project))
        self.produce_hint = label(MSG_NEED_ALL, "hint")
        self.produce_hint.setAlignment(Qt.AlignRight)
        production = QFrame()
        production.setObjectName("productionBar")
        production.setFixedHeight(88)
        production.setLayout(hbox(vbox(label("Ruang", "secondary"), 6, self.room), 32,
                                  vbox(label("Jumlah Reverb", "secondary"), 6, self.amount), None,
                                  vbox(self.produce_btn, 4, self.produce_hint), margins=(24, 8, 24, 8)))
        self.production = production

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(bar)
        root.addWidget(transport)
        root.addWidget(self.banner)
        root.addWidget(scroll, 1)
        root.addWidget(production)

        self.toast = Toast(self)
        self.error_overlay = DeviceErrorOverlay(self)
        self.error_overlay.reconnectRequested.connect(self._reconnect)
        self.guide = VocalGuideOverlay(self)
        self.guide.finished.connect(self._guide_finished)
        self.guide.closed.connect(self._guide_closed)
        self.guide.playPianoRequested.connect(self._toggle_play)
        self._guide_track: str | None = None

        QShortcut(QKeySequence(Qt.Key_Space), self, activated=self._toggle_play,
                  context=Qt.WidgetWithChildrenShortcut)
        QShortcut(QKeySequence(Qt.Key_R), self, activated=lambda: self.record(self.selected_track),
                  context=Qt.WidgetWithChildrenShortcut)

        # Spasi & R adalah shortcut layar; tombol tidak boleh "menelan" Spasi lewat fokus keyboard.
        for b in self.findChildren(QAbstractButton) + self.findChildren(QSlider):
            b.setFocusPolicy(Qt.NoFocus)

        self.timer = QTimer(self)
        self.timer.setInterval(1000 // FPS)
        self.timer.timeout.connect(self._tick)

    @staticmethod
    def _round_button(icon_name: str, tip: str, variant: str) -> QPushButton:
        b = button("", variant)
        b.setIcon(icons.icon(icon_name, "#FFFFFF" if variant == "transportPlay" else COLORS["text2"], 22))
        b.setFixedSize(56, 56)
        b.setIconSize(QSize(24, 24))
        b.setToolTip(tip)
        return b

    # ----- proyek -----
    def show_project(self, project: Project, settings: AppSettings) -> None:
        self.shutdown()
        self.project = project
        self.settings = settings
        self.controller = self.controller_factory(project, settings)
        self.controller.connect_device()
        self.title.setText(project.title)
        self.title.setToolTip(project.title)
        self.tempo_box.value.setText(f"{project.tempo} BPM")
        self.ts_box.value.setText(project.time_signature)
        self.count_box.value.setText("Tanpa" if project.count_in_bars == 0 else f"{project.count_in_bars} Bar")
        self.metronome_btn.blockSignals(True)
        self.metronome_btn.setChecked(project.metronome_after_count_in)
        self.metronome_btn.blockSignals(False)
        self._style_metronome()
        self.metro_slider.setValue(settings.metronome_volume)
        self.room.set_value(project.room_preset)
        self.amount.set_value(project.reverb_amount)
        for tid, strip in self.strips.items():
            strip.set_input_text(input_text(tid, settings))
            strip.waveform.set_peaks(None)
        first_empty = next((t for t in TRACK_IDS if not project.tracks[t].has_audio), "piano")
        self.select_track(first_empty)
        self.refresh_tracks()
        self._update_pill()
        self.controller.start_monitor()
        self._apply_mode(IDLE)
        self.timer.start()

    def refresh_tracks(self) -> None:
        if self.project is None:
            return
        recording = self.controller.record_track if self.controller and self.controller.mode in (
            RECORDING, PREPARING) else None
        for tid, strip in self.strips.items():
            track = self.project.tracks[tid]
            is_rec = tid == recording
            take_id = self.controller.session.take_id if is_rec and self.controller.session else None
            strip.show_track(track, recording=is_rec, recording_take=take_id or self._next_take_id(tid))
            if not is_rec:
                take = track.active_take
                if take is None:
                    strip.waveform.set_peaks(None)
                    strip.waveform.loading = False
                else:
                    peaks = self.peaks.get(self.project.take_path(take))
                    strip.waveform.loading = peaks is None
                    strip.waveform.set_peaks(peaks)
        done = all(self.project.tracks[t].has_audio for t in TRACK_IDS)
        self.produce_btn.setEnabled(done and not self._busy())
        self.produce_hint.setVisible(not done)
        self._update_view_length()

    def _next_take_id(self, track_id: str) -> int:
        return max((t.id for t in self.project.tracks[track_id].takes), default=0) + 1

    def _peaks_ready(self, path, peaks) -> None:
        if self.project is None:
            return
        for tid, strip in self.strips.items():
            take = self.project.tracks[tid].active_take
            if take is not None and self.project.take_path(take) == path:
                strip.waveform.loading = False
                strip.waveform.set_peaks(peaks)
        self._update_view_length()

    def _active_peaks(self, track_id: str):
        take = self.project.tracks[track_id].active_take
        if take is None:
            return None
        return self.peaks.get(self.project.take_path(take))

    def _update_view_length(self, position: float = 0.0) -> None:
        durations = [t.active_take.duration for t in self.project.tracks.values() if t.active_take]
        seconds = view_seconds_for(durations, position)
        for strip in self.strips.values():
            strip.waveform.set_view_seconds(seconds)

    def _update_project(self, **changes) -> None:
        if self.project is not None:
            self.project.update_settings(**changes)

    # ----- pilih track -----
    def select_track(self, track_id: str) -> None:
        if self._busy():
            return
        self.selected_track = track_id
        for tid, strip in self.strips.items():
            strip.set_selected(tid == track_id)

    # ----- transport -----
    def _busy(self) -> bool:
        return self.controller is not None and self.controller.busy

    def _toggle_play(self) -> None:
        if self.controller is None:
            return
        if self.controller.busy:
            self.stop()
        else:
            self.play()

    def play(self) -> None:
        if self.controller is None or self.controller.busy:
            return
        if self.controller.selection is None:
            self.error_overlay.show_missing(self.controller.device_error or "Sound card tidak ditemukan.")
            return
        if not any(t.has_audio for t in self.project.tracks.values()):
            self.toast.show_message("Belum ada track yang direkam.")
            return
        self.controller.play()

    def stop(self) -> None:
        if self.controller is not None:
            self.controller.stop()

    def _to_start(self) -> None:
        if self.controller is not None and not self.controller.busy:
            self.controller.position = 0.0

    def _restart_playback(self) -> None:
        """Ubahan solo/mute/volume saat memutar: campuran dibuat ulang dari posisi sekarang."""
        if self.controller is not None and self.controller.mode == PLAYING:
            position = self.controller.session.song_seconds
            self.controller.stop()
            self.controller.play(max(0.0, position))

    # ----- rekam -----
    def record(self, track_id: str) -> None:
        if self.controller is None or self.controller.busy or self.project is None:
            return
        if self.controller.selection is None:
            self.error_overlay.show_missing(self.controller.device_error or "Sound card tidak ditemukan.")
            return
        allowed, reason = self.project.can_record(track_id)
        if not allowed:
            self.toast.show_message(reason)
            return
        self.select_track(track_id)
        first_vocal = not any(self.project.tracks[t].takes for t in VOCAL_TRACK_IDS)
        if track_id in VOCAL_TRACK_IDS and first_vocal and not self.project.vocal_guide_done:
            self._guide_track = track_id
            self.guide.open_for(input_text(track_id, self.settings).replace("Mic", "Mono"))
            return
        self._start_recording(track_id)

    def _start_recording(self, track_id: str) -> None:
        warning = self.controller.disk_warning()
        if warning:
            answer = QMessageBox.question(self, "Ruang disk hampir penuh", f"{warning}\n\nTetap merekam?")
            if answer != QMessageBox.Yes:
                return
        self.controller.record(track_id)
        self.strips[track_id].waveform.start_live()
        self._apply_mode(PREPARING)

    def _guide_finished(self) -> None:
        if self.controller and self.controller.mode == PLAYING:
            self.controller.stop()
        self.project.update_settings(vocal_guide_done=True)
        track, self._guide_track = self._guide_track, None
        if track:
            QTimer.singleShot(50, lambda: self._start_recording(track))

    def _guide_closed(self) -> None:
        self._guide_track = None
        if self.controller and self.controller.mode == PLAYING:
            self.controller.stop()

    # ----- mixer & take -----
    def _solo(self, track_id: str, on: bool) -> None:
        self.project.set_solo(track_id, on)
        self._restart_playback()

    def _mute(self, track_id: str, on: bool) -> None:
        self.project.set_mute(track_id, on)
        self._restart_playback()

    def _volume(self, track_id: str, db: float) -> None:
        self.project.set_volume(track_id, db)
        if not self.strips[track_id].volume.isSliderDown():
            self._restart_playback()

    def _open_takes(self, track_id: str) -> None:
        if self._busy() and self.controller.mode != PREVIEW:
            return
        track = self.project.tracks[track_id]
        if not track.takes:
            return
        playing = self.controller.preview_take if self.controller.mode == PREVIEW else None
        panel = TakePanel(track, playing, self)
        panel.takeChosen.connect(lambda t: self._choose_take(track_id, t))
        panel.previewRequested.connect(lambda t: self._preview(track_id, t))
        panel.retakeRequested.connect(lambda: self.record(track_id))
        anchor = self.strips[track_id].take_button
        pos = anchor.mapToGlobal(QPoint(0, anchor.height() + 6))
        panel.adjustSize()
        screen = anchor.screen().availableGeometry()
        if pos.y() + panel.height() > screen.bottom():
            pos = anchor.mapToGlobal(QPoint(0, -panel.height() - 6))
        panel.move(pos)
        panel.show()
        self._take_panel = panel

    def _choose_take(self, track_id: str, take_id: int) -> None:
        self.project.set_active_take(track_id, take_id)
        self.refresh_tracks()

    def _preview(self, track_id: str, take_id: int) -> None:
        if self.controller.mode == PREVIEW:
            same = self.controller.preview_take == take_id
            self.controller.stop()
            if same:
                return
            QTimer.singleShot(100, lambda: self.controller.preview(track_id, take_id))
            return
        if self.controller.selection is None:
            self.error_overlay.show_missing(self.controller.device_error or "Sound card tidak ditemukan.")
            return
        self.controller.preview(track_id, take_id)

    def _clip_reset(self, track_id: str) -> None:
        first, count = self.controller.input_channels_for(track_id)
        self.controller.reset_clip(list(range(first, first + count)))

    # ----- metronom -----
    def _metronome_toggled(self, on: bool) -> None:
        self._update_project(metronome_after_count_in=on)
        self._style_metronome()

    def _style_metronome(self) -> None:
        on = self.metronome_btn.isChecked()
        self.metronome_btn.setIcon(icons.icon("metronome", COLORS["blue"] if on else COLORS["text2"], 20))
        self.metronome_btn.setToolTip("Metronom berbunyi selama lagu" if on else
                                      "Metronom hanya berbunyi saat hitungan awal")

    def _metronome_volume_changed(self) -> None:
        self.settings.metronome_volume = self.metro_slider.value()
        save_settings(self.settings)

    # ----- perangkat -----
    def _update_pill(self) -> None:
        ok = self.controller is not None and self.controller.selection is not None
        self.status_pill.setText(self.controller.status_text() if self.controller else "")
        self.status_pill.setIcon(icons.icon("dot", COLORS["green"] if ok else COLORS["red"], 12))
        self.status_pill.setProperty("ok", ok)
        refresh_style(self.status_pill)
        ms, calibrated = self.controller.latency_ms() if ok else (None, False)
        self.status_pill.setToolTip("Latensi dari kalibrasi." if calibrated else
                                    "Belum dikalibrasi: buka Pengaturan > Kalibrasi Latensi." if ok else
                                    "Klik untuk menghubungkan ulang.")

    def _pill_clicked(self) -> None:
        if self.controller is not None and self.controller.selection is None and not self._busy():
            self.error_overlay.show_missing(self.controller.device_error or "Sound card tidak ditemukan.")

    def _reconnect(self) -> None:
        self.error_overlay.set_retrying(True)

        def attempt():
            if self.controller.connect_device(refresh=True):
                self.error_overlay.close_overlay()
                self.controller.start_monitor()
                self.toast.show_message(f"{self.controller.card_name} tersambung kembali.")
            else:
                self.error_overlay.show_retry_failed(self.controller.device_error or "")
            self._update_pill()

        QTimer.singleShot(60, attempt)

    def _open_settings(self) -> None:
        if self._busy():
            return
        self.suspend()
        self.settingsRequested.emit()

    def suspend(self) -> None:
        """Lepaskan sound card (mis. saat layar Pengaturan dibuka)."""
        self.timer.stop()
        if self.controller is not None:
            if self.controller.busy:
                self.controller.stop()
            self.controller.stop_monitor()

    def resume(self, settings: AppSettings) -> None:
        if self.project is not None:
            self.show_project(self.project, settings)

    def _go_back(self) -> None:
        self.shutdown()
        self.backRequested.emit()

    def shutdown(self) -> None:
        self.timer.stop()
        if self.controller is not None:
            self.controller.shutdown()
            self.controller = None

    # ----- tampilan sesuai mode -----
    def _apply_mode(self, mode: str) -> None:
        recording = mode == RECORDING or (mode == PREPARING and self.controller.record_track is not None)
        busy = mode != IDLE
        for w in self._dimmed:
            w.setGraphicsEffect(None)
        self._dimmed = []

        def dim(w: QWidget) -> None:
            effect = QGraphicsOpacityEffect(w)
            effect.setOpacity(0.4)
            w.setGraphicsEffect(effect)
            self._dimmed.append(w)

        rec_track = self.controller.record_track if recording else None
        for tid, strip in self.strips.items():
            strip.setEnabled(not recording or tid == rec_track)
            if recording and tid != rec_track:
                dim(strip)
            strip.record.setEnabled(not busy or tid == rec_track)
            strip.solo.setEnabled(not recording)
            strip.mute.setEnabled(not recording)
            strip.volume.setEnabled(not recording)
            strip.take_button.setEnabled(not recording and bool(self.project.tracks[tid].takes))
        self.production.setEnabled(not busy)
        if recording:
            dim(self.production)
        for w in (self.to_start, self.play_btn, self.metronome_btn, self.metro_slider, self._settings_btn,
                  self._back_btn):
            w.setEnabled(not busy)
        self.stop_btn.setProperty("active", busy)
        self.stop_btn.setIcon(icons.icon("stop", COLORS["app"] if busy else COLORS["text2"], 22))
        refresh_style(self.stop_btn)
        self.play_btn.setProperty("playing", mode == PLAYING)
        refresh_style(self.play_btn)
        self.banner.setVisible(recording)
        if recording:
            self.banner_text.setText(f"● MEREKAM — {self.project.track(rec_track).label.upper()}")
        self.clock.setProperty("recording", recording)
        refresh_style(self.clock)
        self.refresh_tracks()

    # ----- 30 fps -----
    def _tick(self) -> None:
        if self.controller is None:
            return
        st = self.controller.poll()
        if st.mode != self._last_mode or st.stopped:
            self._last_mode = st.mode
            self._apply_mode(st.mode)
        if st.error:
            self.toast.show_message(f"Gagal memulai: {st.error}", error=True, ms=8000)
            self._update_pill()
        if st.finished is not None:
            take = st.finished
            note = "" if take.complete else " (tidak lengkap)"
            self.toast.show_message(" ".join([f"Take {take.id} tersimpan{note}."] + st.warnings),
                                    error=not take.complete, ms=8000 if st.warnings else 4000)
            self.refresh_tracks()
            self._advance_selection()
        elif st.warnings:
            self.toast.show_message(" ".join(st.warnings), ms=8000)
        if st.loss is not None:
            self._update_pill()
            self.error_overlay.show_loss(st.loss.card, st.loss.track_label, st.loss.saved_seconds)
            self.refresh_tracks()

        pos = st.position
        if st.warming_up:
            pos = -st.count_in_seconds  # jam berhenti di awal hitungan selama pemanasan
        self.clock.setText(fmt_clock(pos))
        recording = st.mode == RECORDING
        rec_track = self.controller.record_track if recording else None
        if recording:
            self._blink = (self._blink + 1) % FPS
            self.strips[rec_track].record.blink_on = self._blink < FPS // 2
            self.strips[rec_track].record.update()
            beats = math.ceil(-pos * self.project.tempo / 60) if pos < 0 else 0
            if st.warming_up:
                hint = MSG_WARMING_UP
            else:
                hint = f"Hitungan awal … {beats}" if pos < 0 else "Tekan Stop untuk selesai"
            self.banner_hint.setText(hint)
            self._update_view_length(pos)

        # Meter & playhead
        playing = st.mode in (PLAYING, RECORDING, PREVIEW)
        input_db = to_dbfs(st.input_peaks)
        audible = {t.track_id for t in audible_tracks([
            TrackAudio(tid, None, tr.volume_db, tr.solo, tr.mute) for tid, tr in self.project.tracks.items()
            if tr.has_audio and tid != rec_track])}
        for tid, strip in self.strips.items():
            first, count = self.controller.input_channels_for(tid)
            channels = slice(first, first + count)
            if tid == rec_track or (st.mode == IDLE and tid == self.selected_track):
                level = float(input_db[channels].max()) if len(input_db[channels]) else -120.0
                strip.meter.set_level(level, bool(st.input_clip[channels].any()))
                if tid == rec_track and pos >= 0:
                    strip.waveform.append_live(pos, float(st.input_peaks[channels].max()))
            elif playing and st.mode != PREVIEW and tid in audible:
                peak = peak_at(self._active_peaks(tid), pos) * db_to_gain(self.project.tracks[tid].volume_db)
                strip.meter.set_level(float(to_dbfs(peak)), peak >= 0.999)
            else:
                strip.meter.set_level(-120.0)
            show_head = playing and st.mode != PREVIEW or (st.mode == IDLE and pos > 0)
            strip.waveform.set_playhead(pos if show_head else None,
                                        COLORS["red"] if tid == rec_track else "#FFFFFF")

        if self.guide.isVisible() and self._guide_track:
            first, count = self.controller.input_channels_for(self._guide_track)
            self.guide.update_level(float(input_db[first:first + count].max()))
            self.guide.piano_btn.setText("  Stop" if st.mode == PLAYING else "  Putar Piano")

    def _advance_selection(self) -> None:
        nxt = next((t for t in TRACK_IDS if not self.project.tracks[t].has_audio), None)
        if nxt:
            self.select_track(nxt)


__all__ = ["RecordingScreen", "fmt_clock", "input_text", "QHBoxLayout"]
