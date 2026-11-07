"""Sesi audio: putar campuran monitoring + metronom sambil (opsional) merekam satu track.

Garis waktu lagu: frame 0 = awal birama setelah count-in. Stream dimulai
`count_in_frames` sebelum frame 0, jadi selama count-in posisi lagu negatif.
Saat merekam, stream bisa dimulai `warmup_frames` lebih awal lagi (hening, tidak
direkam): driver USB generik (mis. SC202HD) sering menggeser latensinya dalam
detik-detik pertama stream, dan pergeseran itu tidak dilaporkan PortAudio.

Callback hanya: menyalin buffer putar ke output, menambah klik metronom,
menghitung puncak input, dan menyalin input ke ring buffer perekam. Semua
persiapan berat (memuat & mencampur track, membuat file) dilakukan sebelum
stream dimulai.

Kompensasi latensi: sinyal yang dikirim ke output pada frame lagu p baru
terekam di input pada frame p + L (L = latensi round-trip). Perekam karena itu
mulai menyimpan input pada frame lagu L, sehingga sampel pertama file take
sejajar dengan frame 0 track lain. Pergeseran dilakukan saat merekam, bukan
setelahnya, agar file di disk selalu sudah sejajar (aman jika listrik padam).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

from chorale.audio.calibration import find_calibration
from chorale.audio.device import (
    DEFAULT_BLOCKSIZE, MSG_DEVICE_LOST, SAMPLE_RATE, DeviceSelection, open_duplex_stream,
)
from chorale.audio.meter import LevelMeter, to_dbfs
from chorale.audio.metronome import DEFAULT_VOLUME_DB, Metronome
from chorale.audio.player import Player, build_monitor_mix
from chorale.audio.recorder import Recorder, check_free_space
from chorale.project.model import Project, Take

log = logging.getLogger("chorale.audio")

_FLAGS = ("input_overflow", "input_underflow", "output_underflow", "output_overflow")
COMPLETE_RATIO = 0.9
WARMUP_SECONDS = 5.0  # pemanasan sebelum hitungan awal saat merekam (uji SC202HD 07-11-2026)

MSG_NO_CALIBRATION = (
    "Belum ada kalibrasi latensi untuk sound card ini (buffer {blocksize}). Dipakai perkiraan "
    "driver ({ms:.1f} ms), sehingga track bisa sedikit tidak sejajar. Jalankan kalibrasi "
    "latensi agar selisih antar-track <= 3 ms."
)
MSG_TOO_SHORT = (
    "Take ini lebih pendek dari 90% durasi piano, jadi ditandai tidak lengkap."
)
MSG_NO_REFERENCE = (
    "Kanal acuan tidak terdeteksi, jadi take disejajarkan memakai kalibrasi. "
    "Periksa kabel dari Output ke Input acuan dan pastikan gain-nya tidak nol."
)
REFERENCE_SUFFIX = "_acuan.wav"
ALIGN_CALIBRATION, ALIGN_REFERENCE = "kalibrasi", "acuan"


@dataclass(frozen=True)
class SessionStatus:
    song_seconds: float  # negatif selama count-in
    peaks_db: np.ndarray
    clip: np.ndarray
    dropouts: int
    device_lost: bool
    recorder_error: str | None
    recorded_seconds: float

    @property
    def in_count_in(self) -> bool:
        return self.song_seconds < 0


class AudioSession:
    """Satu kali tekan Putar atau Rekam, sampai Stop."""

    def __init__(
        self,
        project: Project,
        selection: DeviceSelection,
        record_track: str | None = None,
        blocksize: int = DEFAULT_BLOCKSIZE,
        input_first_channel: int = 0,
        record_channels: int | None = None,
        monitor_gain_db: float = 0.0,
        metronome: bool | None = None,
        metronome_volume_db: float = DEFAULT_VOLUME_DB,
        count_in: bool | None = None,
        start_seconds: float = 0.0,
        latency_samples: int | None = None,
        calibration_path: Path | None = None,
        device_timeout: float = 1.0,
        stream_factory=open_duplex_stream,
        playback_mix: np.ndarray | None = None,
        warmup_seconds: float = 0.0,
        reference_channel: int | None = None,
    ):
        """
        metronome: klik selama lagu (None = ikuti pengaturan proyek).
        count_in: pakai hitungan awal (None = ya saat merekam, tidak saat hanya memutar).
        latency_samples: paksa nilai latensi; None = dari kalibrasi, atau perkiraan driver.
        playback_mix: buffer stereo yang diputar sebagai ganti campuran proyek (mis. pratinjau satu take).
        warmup_seconds: hening sebelum hitungan awal, hanya saat merekam (lihat WARMUP_SECONDS).
        reference_channel: kanal input (berbasis 0) yang tersambung kabel ke output; jika diisi,
            take disejajarkan memakai kanal acuan saat Stop (lihat chorale.audio.alignment).
        """
        self.project = project
        self.selection = selection
        self.record_track = record_track
        self.blocksize = blocksize
        self.device_timeout = device_timeout
        self._stream_factory = stream_factory
        self.warnings: list[str] = []

        if record_track is not None:
            allowed, reason = project.can_record(record_track)
            if not allowed:
                raise ValueError(reason)
            space = check_free_space(project.takes_dir)
            if not space.ok:
                self.warnings.append(space.message)
            if record_channels is None:
                record_channels = min(project.track(record_track).channels, selection.input_channels)
            if input_first_channel + record_channels > selection.input_channels:
                raise ValueError("Kanal input yang dipilih melebihi jumlah input sound card.")

        if count_in is None:
            count_in = record_track is not None
        self.metronome = Metronome(
            project.tempo, project.time_signature,
            count_in_bars=project.count_in_bars if count_in else 0,
            click_during_song=project.metronome_after_count_in if metronome is None else metronome,
            volume_db=metronome_volume_db,
        )
        self.count_in_frames = self.metronome.count_in_frames
        self.warmup_frames = int(round(warmup_seconds * SAMPLE_RATE)) if record_track is not None else 0

        # Latensi dari kalibrasi (jika ada); jika tidak, diisi dari driver saat start().
        self.latency_samples = latency_samples
        self.latency_source = "diatur manual" if latency_samples is not None else None
        if record_track is not None and latency_samples is None:
            cal = find_calibration(selection.input.name, selection.output.name, selection.hostapi,
                                   selection.exclusive, blocksize, path=calibration_path)
            if cal is not None:
                self.latency_samples = cal.latency_samples
                self.latency_source = "kalibrasi"

        # Persiapan berat dilakukan di sini, sebelum stream berjalan.
        if playback_mix is None:
            playback_mix = build_monitor_mix(project, exclude=record_track, gain_db=monitor_gain_db)
        self.player = Player(playback_mix)
        start_frame = int(round(start_seconds * SAMPLE_RATE)) if record_track is None else 0
        self.player.seek(start_frame - self.count_in_frames - self.warmup_frames)
        self._song_frame = start_frame - self.count_in_frames - self.warmup_frames
        self.meter = LevelMeter(selection.input_channels)
        self.recorder: Recorder | None = None
        self.take_id: int | None = None
        self._recorded_at: datetime | None = None
        self.reference_recorder: Recorder | None = None
        if record_track is not None:
            self._recorded_at = datetime.now()
            self.take_id, path = project.next_take_path(record_track, self._recorded_at)
            self.recorder = Recorder(path, record_channels, first_channel=input_first_channel)
            if reference_channel is not None:
                used = range(input_first_channel, input_first_channel + record_channels)
                if reference_channel in used or reference_channel >= selection.input_channels:
                    raise ValueError("Kanal acuan harus input lain yang tidak dipakai untuk merekam.")
                self.reference_recorder = Recorder(path.with_name(path.stem + REFERENCE_SUFFIX), 1,
                                                   first_channel=reference_channel)

        self._flag_counts = np.zeros(len(_FLAGS), dtype=np.int64)
        self._stream = None
        self._last_callback = 0.0
        self._finished = False
        self._stopped = False

    # ----- callback audio -----
    def _callback(self, indata, outdata, frames, time_info, status):
        self._last_callback = time.monotonic()
        if status:
            for i, name in enumerate(_FLAGS):
                if getattr(status, name):
                    self._flag_counts[i] += 1
        song_start = self._song_frame
        self.player.process_output(outdata)
        self.metronome.render(outdata, song_start)
        self.meter.update(indata)
        if self.recorder is not None:
            skip = self.latency_samples - song_start
            if skip < frames:
                block = indata[skip:] if skip > 0 else indata
                self.recorder.process_input(block)
                if self.reference_recorder is not None:
                    self.reference_recorder.process_input(block)
        self._song_frame = song_start + frames

    def _on_finished(self):
        self._finished = True

    # ----- kendali -----
    def start(self) -> None:
        if self.recorder is not None:
            self.recorder.start()
        if self.reference_recorder is not None:
            self.reference_recorder.start()
        try:
            self._stream = self._stream_factory(self.selection, self._callback, self.blocksize,
                                                finished_callback=self._on_finished)
            if self.latency_samples is None:
                reported = sum(getattr(self._stream, "latency", (0.0, 0.0)))
                self.latency_samples = int(round(reported * SAMPLE_RATE))
                self.latency_source = "perkiraan driver"
                if self.record_track is not None:
                    self.warnings.append(MSG_NO_CALIBRATION.format(
                        blocksize=self.blocksize, ms=reported * 1000))
            self._last_callback = time.monotonic()
            self._stream.start()
        except Exception:
            if self._stream is not None:
                self._stream.close()
            if self.recorder is not None:
                self._discard_empty(self.recorder.stop())
            self._remove_reference()
            raise

    @property
    def song_seconds(self) -> float:
        return self._song_frame / SAMPLE_RATE

    @property
    def count_in_seconds(self) -> float:
        return self.count_in_frames / SAMPLE_RATE

    @property
    def warming_up(self) -> bool:
        """Masih dalam pemanasan (sebelum hitungan awal dimulai)."""
        return self._song_frame < -self.count_in_frames

    @property
    def device_lost(self) -> bool:
        if self._stream is None or self._stopped:
            return False
        return self._finished or (time.monotonic() - self._last_callback > self.device_timeout)

    @property
    def dropouts(self) -> int:
        return int(self._flag_counts.sum())

    @property
    def cpu_load(self) -> float:
        try:
            return float(self._stream.cpu_load)
        except Exception:  # noqa: BLE001 - stream palsu atau sudah ditutup
            return 0.0

    @property
    def playback_length_seconds(self) -> float:
        return self.player.length_frames / SAMPLE_RATE

    def status(self) -> SessionStatus:
        return SessionStatus(
            song_seconds=self.song_seconds,
            peaks_db=to_dbfs(self.meter.read()),
            clip=self.meter.clip(),
            dropouts=self.dropouts,
            device_lost=self.device_lost,
            recorder_error=self.recorder.error if self.recorder else None,
            recorded_seconds=(self.recorder.frames_written / SAMPLE_RATE) if self.recorder else 0.0,
        )

    def stop(self) -> Take | None:
        """Hentikan sesi. Jika merekam, daftarkan take baru dan kembalikan."""
        lost = self.device_lost
        self._stopped = True
        if self._stream is not None:
            try:
                self._stream.stop()
            except Exception:  # noqa: BLE001 - perangkat mungkin sudah hilang
                lost = True
            try:
                self._stream.close()
            except Exception:  # noqa: BLE001
                pass
        if self.recorder is None:
            return None
        result = self.recorder.stop()
        if self._discard_empty(result):
            self._remove_reference()
            return None

        complete = not lost and result.error is None
        piano = self.project.tracks["piano"].active_take
        if self.record_track != "piano" and piano is not None and result.duration < COMPLETE_RATIO * piano.duration:
            complete = False
            self.warnings.append(MSG_TOO_SHORT)
        duration = result.duration
        latency = self.latency_samples or 0
        alignment = ALIGN_CALIBRATION
        if self.reference_recorder is not None:
            aligned = self._align_with_reference(result.path)
            if aligned is not None:
                duration = aligned.frames / SAMPLE_RATE
                latency += aligned.offset
                alignment = ALIGN_REFERENCE
        take = Take(
            id=self.take_id,
            filename=result.path.name,
            recorded_at=self._recorded_at.isoformat(timespec="seconds"),
            duration=round(duration, 3),
            complete=complete,
            latency_compensation=latency,
            alignment=alignment,
        )
        self.project.add_take(self.record_track, take)
        if lost:
            self.warnings.append(MSG_DEVICE_LOST)
        if result.error:
            self.warnings.append(result.error)
        return take

    def played_reference(self, frames: int) -> np.ndarray:
        """Sinyal yang keluar dari output mulai frame lagu 0 (campuran monitoring + klik), mono."""
        mix = self.player._mix  # noqa: SLF001 - buffer yang sama yang diputar callback
        out = np.zeros(frames, dtype=np.float32)
        n = min(frames, len(mix))
        if n > 0:
            out[:n] = mix[:n].mean(axis=1)
        out += self.metronome.click_train(frames)
        return out

    def _align_with_reference(self, take_path: Path):
        """Sejajarkan take dengan kanal acuan; hapus berkas acuan. None = acuan tidak terdeteksi."""
        from chorale.audio.alignment import align_take

        ref = self.reference_recorder.stop()
        try:
            if ref.frames == 0 or ref.error:
                self.warnings.append(MSG_NO_REFERENCE)
                return None
            aligned = align_take(take_path, ref.path, self.played_reference(ref.frames + SAMPLE_RATE))
            if aligned is None:
                self.warnings.append(MSG_NO_REFERENCE)
            return aligned
        except Exception:  # noqa: BLE001 - take hasil kalibrasi tetap utuh
            log.exception("Penyejajaran kanal acuan gagal untuk %s", take_path.name)
            self.warnings.append(MSG_NO_REFERENCE)
            return None
        finally:
            ref.path.unlink(missing_ok=True)

    def _remove_reference(self) -> None:
        if self.reference_recorder is not None:
            self.reference_recorder.stop().path.unlink(missing_ok=True)

    @staticmethod
    def _discard_empty(result) -> bool:
        """Hapus file take buatan sesi ini jika tidak berisi audio sama sekali."""
        if result.frames == 0:
            result.path.unlink(missing_ok=True)
            return True
        return False


__all__ = ["AudioSession", "SessionStatus", "SAMPLE_RATE"]
