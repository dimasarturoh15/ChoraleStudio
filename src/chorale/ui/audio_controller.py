"""Penghubung layar perekaman dengan engine audio (Segmen 2–3).

Aturan: callback audio tidak pernah memancarkan sinyal Qt. Layar membaca keadaan
lewat poll() dari QTimer 30 fps. Persiapan sesi yang berat (memuat & mencampur
take) dikerjakan di thread pekerja; poll() mengambil hasilnya bila sudah siap.
"""

from __future__ import annotations

import logging
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from chorale.audio import device as dev
from chorale.audio.calibration import find_calibration
from chorale.audio.meter import to_dbfs
from chorale.audio.monitor import InputMonitor
from chorale.audio.player import load_take_audio
from chorale.audio.recorder import check_free_space
from chorale.audio.session import WARMUP_SECONDS, AudioSession
from chorale.project.model import Project, Take
from chorale.settings import AppSettings

IDLE, PREPARING, PLAYING, RECORDING, PREVIEW = "idle", "preparing", "playing", "recording", "preview"
log = logging.getLogger("chorale.audio")
AUTO_STOP_TAIL_S = 2.0


@dataclass
class DeviceLoss:
    """Keterangan saat sound card terputus."""

    card: str
    track_label: str | None = None   # track yang sedang direkam (None jika sedang memutar)
    saved_seconds: float = 0.0
    take: Take | None = None


@dataclass
class PollState:
    mode: str
    position: float
    input_peaks: np.ndarray            # linear, per kanal input sound card
    input_clip: np.ndarray
    recorded_seconds: float = 0.0
    warming_up: bool = False           # pemanasan sound card sebelum hitungan awal
    count_in_seconds: float = 0.0
    finished: Take | None = None       # take yang baru selesai direkam (sekali)
    stopped: bool = False              # sesi baru saja berhenti (sekali)
    loss: DeviceLoss | None = None     # sound card terputus (sekali)
    error: str | None = None           # gagal memulai sesi (sekali)
    warnings: list[str] = field(default_factory=list)


class AudioController:
    warmup_seconds = WARMUP_SECONDS  # tes dengan stream palsu boleh mengecilkannya

    def __init__(self, project: Project, settings: AppSettings, stream_factory=None,
                 monitor_factory=InputMonitor):
        """stream_factory/monitor_factory bisa diganti (tes tanpa sound card)."""
        self.project = project
        self.settings = settings
        self._stream_factory = stream_factory
        self._monitor_factory = monitor_factory
        self.selection: dev.DeviceSelection | None = None
        self.device_error: str | None = None
        self.mode = IDLE
        self.position = 0.0          # kursor lagu saat diam (detik)
        self.session: AudioSession | None = None
        self.monitor: InputMonitor | None = None
        self.record_track: str | None = None
        self.preview_take: int | None = None
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="SiapkanSesi")
        self._pending: Future | None = None
        self._pending_mode = IDLE
        self._events: dict = {}

    # ----- perangkat -----
    @property
    def card_name(self) -> str:
        if self.selection is not None:
            return dev.card_name(self.selection.input.name)
        return self.settings.device_name or "sound card"

    def connect_device(self, refresh: bool = False) -> bool:
        """Pilih sound card sesuai pengaturan. refresh=True memindai ulang (setelah dicolok ulang)."""
        self.stop_monitor()
        if refresh:
            try:
                dev.refresh_devices()
            except Exception:  # noqa: BLE001
                pass
        try:
            keywords = self.settings.device_name or dev.TARGET_KEYWORDS
            self.selection = dev.select_device(keywords, mode=self.settings.driver_mode)
            self.device_error = None
            log.info("Sound card: %s / %s (%s)", self.selection.input.name, self.selection.output.name,
                     self.selection.mode_label)
        except dev.AudioDeviceError as exc:
            self.selection = None
            self.device_error = str(exc)
            log.warning("Sound card tidak bisa dipilih: %s %s", exc, getattr(exc, "technical", ""))
        return self.selection is not None

    def latency_ms(self) -> tuple[float | None, bool]:
        """(latensi ms, dari kalibrasi?) untuk pil status."""
        s = self.selection
        if s is None:
            return None, False
        cal = find_calibration(s.input.name, s.output.name, s.hostapi, s.exclusive, self.settings.blocksize)
        if cal is not None:
            return cal.latency_ms, True
        return None, False

    def status_text(self) -> str:
        if self.selection is None:
            return "Sound card tidak tersambung"
        ms, _ = self.latency_ms()
        latency = f" · {ms:.0f} ms" if ms is not None else ""
        return f"{self.selection.mode_label} · 48 kHz · 24-bit{latency}"

    # ----- meter input saat diam -----
    def start_monitor(self) -> None:
        if self.selection is None or self.monitor is not None or self.mode != IDLE:
            return
        try:
            self.monitor = self._monitor_factory(self.selection, self.settings.blocksize)
            self.monitor.start()
        except dev.AudioDeviceError as exc:
            self.monitor = None
            self.device_error = str(exc)

    def stop_monitor(self) -> None:
        if self.monitor is not None:
            self.monitor.stop()
            self.monitor = None

    def reset_clip(self, channels: list[int] | None = None) -> None:
        for meter in self._meters():
            if channels is None:
                meter.reset_clip()
            else:
                for ch in channels:
                    if ch < meter.channels:
                        meter.reset_clip(ch)

    def _meters(self):
        out = []
        if self.monitor is not None:
            out.append(self.monitor.meter)
        if self.session is not None:
            out.append(self.session.meter)
        return out

    # ----- kanal input -----
    def input_channels_for(self, track_id: str) -> tuple[int, int]:
        """(kanal pertama, jumlah kanal) input untuk track."""
        if track_id == "piano":
            first, count = self.settings.instrument_channels()
        else:
            first, count = self.settings.vocal_channel(), 1
        available = self.selection.input_channels if self.selection else 2
        if first + count > available:
            first, count = 0, min(count, available)
        return first, count

    def disk_warning(self) -> str | None:
        space = check_free_space(self.project.takes_dir)
        return None if space.ok else space.message

    # ----- kendali -----
    @property
    def busy(self) -> bool:
        return self.mode != IDLE

    def play(self, start_seconds: float | None = None) -> None:
        self._start(PLAYING, record_track=None, start=self.position if start_seconds is None else start_seconds)

    def record(self, track_id: str) -> None:
        self._start(RECORDING, record_track=track_id, start=0.0)

    def preview(self, track_id: str, take_id: int) -> None:
        take = self.project.track(track_id).get_take(take_id)
        self.preview_take = take_id
        self._start(PREVIEW, record_track=None, start=0.0, preview_path=self.project.take_path(take))

    def _start(self, mode: str, record_track: str | None, start: float, preview_path: Path | None = None) -> None:
        if self.mode != IDLE or self.selection is None:
            return
        self.stop_monitor()
        self.mode = PREPARING
        self._pending_mode = mode
        self.record_track = record_track
        selection, settings, project = self.selection, self.settings, self.project

        def prepare() -> AudioSession:
            kwargs = dict(blocksize=settings.blocksize, metronome_volume_db=settings.metronome_volume_db())
            if self._stream_factory is not None:
                kwargs["stream_factory"] = self._stream_factory
            if record_track is not None:
                first, count = self.input_channels_for(record_track)
                return AudioSession(project, selection, record_track=record_track,
                                    input_first_channel=first, record_channels=count,
                                    warmup_seconds=self.warmup_seconds, **kwargs)
            if preview_path is not None:
                audio = load_take_audio(preview_path)
                mix = np.repeat(audio[:, :1], 2, axis=1) if audio.shape[1] == 1 else audio[:, :2]
                return AudioSession(project, selection, metronome=False, count_in=False,
                                    playback_mix=np.ascontiguousarray(mix, dtype=np.float32), **kwargs)
            return AudioSession(project, selection, count_in=False, start_seconds=start, **kwargs)

        self._pending = self._pool.submit(prepare)

    def stop(self) -> None:
        """Stop/Putar-ulang: hentikan sesi apa pun. Hasil (take, peringatan) muncul di poll() berikutnya."""
        if self.mode == PREPARING and self._pending is not None:
            self._pending.cancel()
            self._pending_mode = IDLE
            return
        if self.session is None:
            return
        position = self.session.song_seconds
        take = self.session.stop()
        warnings = list(self.session.warnings)
        if self.mode == PLAYING:
            self.position = max(0.0, position)
        elif self.mode == RECORDING:
            self.position = 0.0
        self._finish(take=take, warnings=warnings)

    def _finish(self, take: Take | None = None, warnings: list[str] | None = None,
                loss: DeviceLoss | None = None) -> None:
        self.session = None
        self.mode = IDLE
        self.record_track = None
        self.preview_take = None
        self._events = {"finished": take, "stopped": True, "warnings": warnings or [], "loss": loss}
        if loss is None:
            self.start_monitor()

    def poll(self) -> PollState:
        """Dipanggil QTimer 30 fps dari thread UI."""
        if self.mode == PREPARING and self._pending is not None and self._pending.done():
            future, self._pending = self._pending, None
            if self._pending_mode == IDLE or future.cancelled():
                self.mode = IDLE
                self.record_track = None  # Stop ditekan saat sesi masih disiapkan
                self.start_monitor()
            else:
                try:
                    self.session = future.result()
                    self.session.start()
                    self.mode = self._pending_mode
                except Exception as exc:  # noqa: BLE001
                    log.exception("Gagal memulai sesi audio (%s)", self._pending_mode)
                    self.session = None
                    self.mode = IDLE
                    self.record_track = None
                    self._events = {"error": getattr(exc, "args", [str(exc)])[0] or str(exc)}
                    self.start_monitor()

        # Sound card hilang?
        if self.session is not None and self.session.device_lost:
            track = self.record_track
            take = self.session.stop()
            # Diukur setelah perekam selesai menulis sisa data ke disk (bukan saat terdeteksi).
            saved = take.duration if take is not None else 0.0
            label = self.project.track(track).label if track else None
            loss = DeviceLoss(self.card_name, label, saved, take)  # nama diambil sebelum selection dikosongkan
            log.warning("Sound card terputus saat %s; tersimpan %.2f s (%s)", self.mode, saved,
                        take.filename if take else "tanpa take")
            self.selection = None
            self.device_error = dev.MSG_DEVICE_LOST
            self._finish(take=take, warnings=[], loss=loss)
        elif self.monitor is not None and not self.monitor.active:
            loss = DeviceLoss(self.card_name)
            self.stop_monitor()
            self.selection = None
            self.device_error = dev.MSG_DEVICE_LOST
            self._events = {"loss": loss}

        # Berhenti otomatis di akhir lagu (putar/pratinjau) atau akhir piano + 2 detik (rekam vokal).
        if self.session is not None:
            pos = self.session.song_seconds
            end = self.session.playback_length_seconds
            if self.mode in (PLAYING, PREVIEW) and pos >= end:
                self.stop()
            elif self.mode == RECORDING and self.record_track != "piano" and end > 0 and pos >= end + AUTO_STOP_TAIL_S:
                self.stop()

        channels = self.selection.input_channels if self.selection else 2
        peaks, clip = np.zeros(channels), np.zeros(channels, dtype=bool)
        meter = self.session.meter if self.session is not None else (self.monitor.meter if self.monitor else None)
        if meter is not None:
            peaks, clip = meter.read(), meter.clip()
        state = PollState(
            mode=self.mode,
            position=self.session.song_seconds if self.session is not None else self.position,
            input_peaks=peaks,
            input_clip=clip,
            recorded_seconds=(self.session.recorder.frames_written / 48000
                              if self.session is not None and self.session.recorder else 0.0),
            warming_up=self.session.warming_up if self.session is not None else False,
            count_in_seconds=self.session.count_in_seconds if self.session is not None else 0.0,
            finished=self._events.get("finished"),
            stopped=self._events.get("stopped", False),
            loss=self._events.get("loss"),
            error=self._events.get("error"),
            warnings=self._events.get("warnings", []),
        )
        self._events = {}
        return state

    def shutdown(self) -> None:
        if self.session is not None:
            self.stop()
        if self._pending is not None:
            self._pending.cancel()
        self.stop_monitor()
        self._pool.shutdown(wait=True, cancel_futures=True)


def peaks_db(peaks: np.ndarray) -> np.ndarray:
    return to_dbfs(peaks)
