"""Layar 'Hasil Produksi' (mockup: harmonisatb_studio_result_export)."""

from __future__ import annotations

import math
import subprocess
from pathlib import Path

from PySide6.QtCore import QSize, QTimer, Qt, Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QPushButton, QScrollArea, QVBoxLayout, QWidget

from chorale.audio import device as dev
from chorale.audio.ab_player import SOURCE_A, SOURCE_B, ABPlayer
from chorale.dsp.presets import CEILING_DBTP, LUFS_TOLERANCE, REVERB_AMOUNT_LABELS, ROOM_PRESETS, TARGET_LUFS
from chorale.settings import AppSettings
from chorale.ui import icons
from chorale.ui.recording_screen import Toast, fmt_clock
from chorale.ui.track_strip import fmt_duration
from chorale.ui.theme import COLORS
from chorale.ui.waveform import WaveformView, peaks_from_array
from chorale.ui.widgets import SegmentedControl, TopBar, button, card, hbox, icon_label, label, refresh_style, vbox

FPS = 30


def open_in_explorer(path: Path) -> None:
    """Buka Windows Explorer dengan file hasil terpilih."""
    subprocess.Popen(["explorer", "/select,", str(path)])


def default_selection(settings: AppSettings) -> dev.DeviceSelection | None:
    try:
        return dev.select_device(settings.device_name or dev.TARGET_KEYWORDS, mode=settings.driver_mode)
    except dev.AudioDeviceError:
        return None


def elide_middle(name: str, max_chars: int = 34) -> str:
    """'Bapa_Engkau_Sungguh_Baik_20261106-1305_Master.wav' -> 'Bapa_Engkau_..._Master.wav' (seperti mockup)."""
    if len(name) <= max_chars:
        return name
    head, _, tail = name.rpartition("_")
    keep = max(6, max_chars - len(tail) - 5)
    return f"{head[:keep]}..._{tail}"


class ReportRow(QWidget):
    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        self.value = label("", "reportValue")
        self.status = QWidget()
        self.status.setFixedSize(18, 18)
        self._icon = icon_label("check", COLORS["green"], 18)
        self._icon.setParent(self.status)
        self._icon.hide()
        self.setLayout(hbox(label(name, "secondary"), None, self.value, 10, self.status, margins=(0, 9, 0, 9)))

    def set(self, value: str, ok: bool | None = None) -> None:
        self.value.setText(value)
        if ok is None:
            self._icon.hide()
        else:
            self._icon.setPixmap(icons.pixmap("check" if ok else "warning", COLORS["green"] if ok else COLORS["yellow"], 18))
            self._icon.show()
            self.status.setToolTip("Target tercapai" if ok else "Target tidak tercapai — lihat catatan")


class FileRow(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("fileRow")
        self.icon = icon_label("file", COLORS["blue"], 20)
        self.name = label("", "fileName")
        self.kind = label("", "hint")
        self.setLayout(hbox(self.icon, 12, self.name, None, 12, self.kind, margins=(16, 9, 16, 9)))

    def set(self, path: Path, kind: str, audio: bool = True) -> None:
        self.name.setText(elide_middle(path.name))
        self.name.setToolTip(str(path))
        self.kind.setText(kind)
        self.icon.setPixmap(icons.pixmap("file", COLORS["blue"] if audio else COLORS["text2"], 20))


class ResultScreen(QWidget):
    backRequested = Signal()
    reprocessRequested = Signal(object)

    selection_factory = staticmethod(default_selection)  # bisa diganti di tes
    stream_factory = None                                  # None = sound card sungguhan
    open_folder = staticmethod(open_in_explorer)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("screen")
        self.project = None
        self.result = None
        self.player: ABPlayer | None = None
        self.selection: dev.DeviceSelection | None = None

        bar = TopBar()
        bar.layout_.setSpacing(16)
        back = button("", "square", "arrow_left", COLORS["text2"], 20)
        back.setToolTip("Kembali ke layar perekaman")
        back.clicked.connect(self._back)
        self.title = label("", "appTitle")
        self.status_pill = QPushButton()
        self.status_pill.setObjectName("statusPill")
        bar.layout_.addWidget(back)
        bar.layout_.addWidget(self.title)
        bar.layout_.addStretch(1)
        bar.layout_.addWidget(self.status_pill)

        badge = label("✓  Master selesai dibuat", "successBadge")

        # ----- pratinjau -----
        self.waveform = WaveformView(COLORS["blue"])
        self.waveform.setMinimumHeight(220)
        self.waveform.shade_played = True
        self.waveform.seekable = True
        self.waveform.seekRequested.connect(self._seek)
        self.play_btn = button("", "bigPlay")
        self.play_btn.setFixedSize(64, 64)
        self.play_btn.setIconSize(QSize(26, 26))
        self.play_btn.clicked.connect(self.toggle_play)
        self.position = label("00:00.000", "bigClock")
        self.total = label("/ 00:00.000", "bigClockTotal")
        self.ab = SegmentedControl([(SOURCE_A, "A · Mentah"), (SOURCE_B, "B · Master")], height=60)
        self.ab.changed.connect(self._source_changed)
        hint = hbox(icon_label("info", COLORS["text2"], 16), 8,
                    label("Volume A dan B disamakan agar perbandingan adil.", "secondary"), None)
        preview = card()
        preview.setLayout(vbox(
            hbox(icon_label("dot", COLORS["blue"], 14), 8, label("Pratinjau Master", "panelTitle"), None,
                 label("24-bit · 48 kHz · Stereo", "mono")), 20,
            self.waveform, 24,
            hbox(self.play_btn, 20, vbox(label("Posisi Waktu", "secondary"), 2,
                                         hbox(self.position, 12, self.total, None)), None), 24,
            self.ab, 12, hint, None, margins=(28, 24, 28, 24)))

        # ----- laporan -----
        self.ready_badge = label("", "readyBadge")
        self.rows = {key: ReportRow(name) for key, name in (
            ("lufs", "Kelantangan"), ("tp", "Puncak (True Peak)"), ("lra", "Rentang Dinamika (LRA)"),
            ("dur", "Durasi"), ("room", "Ruang"))}
        report_lay = QVBoxLayout()
        report_lay.setSpacing(0)
        for i, row in enumerate(self.rows.values()):
            if i:
                sep = QFrame()
                sep.setObjectName("separator")
                report_lay.addWidget(sep)
            report_lay.addWidget(row)
        self.notes = label("", "hint")
        self.notes.setWordWrap(True)
        self.warnings = label("", "warningText")
        self.warnings.setWordWrap(True)
        sep0 = QFrame()
        sep0.setObjectName("separator")
        report = card()
        report.setLayout(vbox(
            hbox(icon_label("bars", COLORS["text2"], 20), 10, label("Laporan Mastering", "h3"), None,
                 self.ready_badge), 10, sep0, 2, report_lay, 4, self.warnings, 4, self.notes,
            margins=(24, 18, 24, 18)))

        # ----- ekspor -----
        self.files = [FileRow(), FileRow(), FileRow()]
        self.count_badge = label("3 berkas", "countBadge")
        self.open_btn = button("Buka Folder Hasil", "primary", "folder", "#FFFFFF", 20)
        self.open_btn.setFixedHeight(52)
        self.open_btn.clicked.connect(self._open_folder)
        sep1 = QFrame()
        sep1.setObjectName("separator")
        export = card()
        export.setLayout(vbox(
            hbox(icon_label("upload", COLORS["text2"], 20), 10, label("Ekspor", "h3"), None, self.count_badge), 10,
            sep1, 12, self.files[0], 8, self.files[1], 8, self.files[2], 14, self.open_btn,
            margins=(24, 18, 24, 18)))

        back2 = button("Kembali & Ubah Pengaturan".replace("&", "&&"), "toolbar", "sliders", COLORS["text2"], 18)
        back2.setFixedHeight(48)
        back2.clicked.connect(self._back)
        redo = button("Proses Ulang", "toolbar", "refresh", COLORS["text2"], 18)
        redo.setFixedHeight(48)
        redo.clicked.connect(self._reprocess)

        # Seperti mockup: tombol bawah di bawah kartu pratinjau (kolom kiri), laporan & ekspor di kanan.
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.addLayout(vbox(preview, None, 20, hbox(back2, 16, redo, None)), 0, 0)
        grid.addLayout(vbox(report, 20, export, None), 0, 1)
        grid.setColumnStretch(0, 5)
        grid.setColumnStretch(1, 4)

        content = QWidget()
        content.setObjectName("scrollContent")
        content.setLayout(vbox(hbox(badge, None), 8, label("Hasil Produksi", "h1"), 18, grid, None,
                               margins=(48, 20, 48, 20)))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(bar)
        root.addWidget(scroll, 1)

        self.toast = Toast(self)
        self.timer = QTimer(self)
        self.timer.setInterval(1000 // FPS)
        self.timer.timeout.connect(self._tick)
        for b in self.findChildren(QPushButton):
            b.setFocusPolicy(Qt.NoFocus)

    # ----- isi -----
    def show_result(self, project, result, settings: AppSettings) -> None:
        self.shutdown()
        self.project, self.result = project, result
        self.title.setText(project.title)
        self.selection = self.selection_factory(settings)
        ok = self.selection is not None
        self.status_pill.setText(f"{self.selection.mode_label} · 48 kHz · 24-bit" if ok else "Sound card tidak tersambung")
        self.status_pill.setIcon(icons.icon("dot", COLORS["green"] if ok else COLORS["red"], 12))
        self.status_pill.setProperty("ok", ok)
        refresh_style(self.status_pill)

        m = result.mastered
        kwargs = {"blocksize": settings.blocksize}
        if self.stream_factory is not None:
            kwargs["stream_factory"] = self.stream_factory
        self.player = ABPlayer(self.selection, result.raw, m.audio, *result.ab_gains_db, **kwargs)
        self.ab.set_value(SOURCE_B)
        self._label_ab()
        self.waveform.set_view_seconds(self.player.length_seconds)
        self.waveform.set_peaks(peaks_from_array(m.audio))
        self.total.setText(f"/ {fmt_clock(self.player.length_seconds)}")

        lufs_ok = abs(m.integrated_lufs - TARGET_LUFS) <= LUFS_TOLERANCE
        tp_ok = m.true_peak_dbtp <= CEILING_DBTP
        self.rows["lufs"].set(f"{m.integrated_lufs:.1f} LUFS" if math.isfinite(m.integrated_lufs) else "—", lufs_ok)
        self.rows["tp"].set(f"{m.true_peak_dbtp:.1f} dBTP", tp_ok)
        self.rows["lra"].set(f"{m.lra_lu:.1f} LU")
        self.rows["dur"].set(fmt_duration(result.duration))
        p = result.production
        self.rows["room"].set(f"{ROOM_PRESETS[p.room].label} · {REVERB_AMOUNT_LABELS[p.reverb_amount]}")
        ready = result.youtube_ready
        self.ready_badge.setText("Siap YouTube" if ready else "Perlu perhatian")
        self.ready_badge.setProperty("ok", ready)
        refresh_style(self.ready_badge)
        self.warnings.setText("\n".join(m.warnings))
        self.warnings.setVisible(bool(m.warnings))
        notes = [w for w in result.warnings if w not in m.warnings]
        self.notes.setText("\n".join(notes))
        self.notes.setVisible(bool(notes))

        if result.wav_path is not None:
            self.files[0].set(result.wav_path, "WAV 24-bit · 48 kHz")
            self.files[1].set(result.mp3_path, "MP3 320 kbps")
            self.files[2].set(result.report_path, "Laporan", audio=False)
        self._update_play_icon()
        self._update_position()
        self.timer.start()

    # ----- putar & A/B -----
    def toggle_play(self) -> None:
        if self.player is None:
            return
        if self.player.playing:
            self.player.pause()
        else:
            try:
                self.player.play()
            except dev.AudioDeviceError as exc:
                self.toast.show_message(str(exc), error=True)
        self._update_play_icon()

    def _seek(self, seconds: float) -> None:
        if self.player is not None:
            self.player.seek(seconds)
            self._update_position()

    def _source_changed(self, source) -> None:
        if self.player is not None:
            self.player.set_source(source)
        self._label_ab()

    def _label_ab(self) -> None:
        current = self.ab.value()
        for key, text in ((SOURCE_A, "A · Mentah"), (SOURCE_B, "B · Master")):
            self.ab.button(key).setText(("✓  " if key == current else "○  ") + text)

    def _update_play_icon(self) -> None:
        playing = self.player is not None and self.player.playing
        self.play_btn.setIcon(icons.icon("stop" if playing else "play", "#FFFFFF", 26))
        self.play_btn.setToolTip("Hentikan" if playing else "Putar")

    def _update_position(self) -> None:
        if self.player is None:
            return
        pos = self.player.position_seconds
        self.position.setText(fmt_clock(pos))
        self.waveform.set_playhead(pos)

    def _tick(self) -> None:
        if self.player is None:
            return
        if self.player.playing and self.player.device_lost:
            self.player.pause()
            self.toast.show_message("Sambungan ke sound card terputus. Periksa kabel USB.", error=True)
        elif self.player.playing and self.player.ended:
            self.player.pause()
            self.player.seek(0)
        self._update_play_icon()
        self._update_position()

    # ----- tombol -----
    def _open_folder(self) -> None:
        if self.result is not None and self.result.wav_path is not None:
            self.open_folder(self.result.wav_path)

    def _back(self) -> None:
        self.shutdown()
        self.backRequested.emit()

    def _reprocess(self) -> None:
        if self.player is not None:
            self.player.pause()
            self._update_play_icon()
        self.reprocessRequested.emit(self.project)

    def shutdown(self) -> None:
        self.timer.stop()
        if self.player is not None:
            self.player.close()
            self.player = None
