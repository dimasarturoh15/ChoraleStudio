"""Perekam ke disk: callback hanya menyalin ke ring buffer, thread terpisah menulis WAV 24-bit.

Header WAV diperbarui dan data di-flush ke disk paling lambat tiap 1 detik,
sehingga jika listrik padam atau sound card dicabut, file tetap bisa dibuka
dan paling banyak ~1 detik terakhir yang hilang.
"""

from __future__ import annotations

import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

SAMPLE_RATE = 48000
MIN_FREE_BYTES = 2 * 1024**3
_SFC_UPDATE_HEADER_NOW = 0x1060


class RingBuffer:
    """Ring buffer satu penulis (callback audio) dan satu pembaca (thread penulis disk).

    Memori dialokasikan sekali di awal. Penulis hanya menyalin data dan
    memajukan penghitung; jika penuh, sisa data dibuang dan dihitung di overrun_frames.
    """

    def __init__(self, capacity_frames: int, channels: int):
        self._buf = np.zeros((capacity_frames, channels), dtype=np.float32)
        self._capacity = capacity_frames
        self._written = 0
        self._read = 0
        self.overrun_frames = 0

    @property
    def available(self) -> int:
        return self._written - self._read

    def write(self, data: np.ndarray) -> None:
        n = len(data)
        free = self._capacity - (self._written - self._read)
        if n > free:
            self.overrun_frames += n - free
            n = free
        start = self._written % self._capacity
        first = min(n, self._capacity - start)
        self._buf[start:start + first] = data[:first]
        if n > first:
            self._buf[:n - first] = data[first:n]
        self._written += n

    def read(self) -> np.ndarray:
        """Ambil semua data yang tersedia (salinan)."""
        n = self._written - self._read
        start = self._read % self._capacity
        first = min(n, self._capacity - start)
        out = np.empty((n, self._buf.shape[1]), dtype=np.float32)
        out[:first] = self._buf[start:start + first]
        out[first:] = self._buf[:n - first]
        self._read += n
        return out


@dataclass(frozen=True)
class RecordingResult:
    path: Path
    frames: int
    overrun_frames: int
    error: str | None

    @property
    def duration(self) -> float:
        return self.frames / SAMPLE_RATE


class Recorder:
    """Rekam kanal input tertentu ke satu file WAV 24-bit 48 kHz."""

    def __init__(self, path: Path, channels: int, first_channel: int = 0,
                 ring_seconds: float = 4.0, flush_interval: float = 1.0):
        self.path = Path(path)
        self.channels = channels
        self._slice = slice(first_channel, first_channel + channels)
        self._ring = RingBuffer(int(ring_seconds * SAMPLE_RATE), channels)
        self._flush_interval = flush_interval
        self._file: sf.SoundFile | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._accepting = False
        self.frames_written = 0
        self.error: str | None = None

    def start(self) -> None:
        if self.path.exists():
            raise FileExistsError(f"File take sudah ada, tidak akan ditimpa: {self.path}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = sf.SoundFile(str(self.path), mode="w", samplerate=SAMPLE_RATE,
                                  channels=self.channels, subtype="PCM_24", format="WAV")
        self._sync()
        self._thread = threading.Thread(target=self._writer_loop, name="RecorderWriter", daemon=True)
        self._accepting = True
        self._thread.start()

    def process_input(self, indata: np.ndarray) -> None:
        """Dipanggil dari callback audio: hanya menyalin ke ring buffer."""
        if self._accepting:
            self._ring.write(indata[:, self._slice])

    def stop(self) -> RecordingResult:
        """Hentikan, tulis sisa data, tutup file. Aman dipanggil walau perangkat sudah mati."""
        self._accepting = False
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        if self._file is not None:
            try:
                self._drain()
                self._file.close()
            except Exception as exc:  # noqa: BLE001
                self.error = self.error or f"Gagal menutup file rekaman: {exc}"
            self._file = None
        return RecordingResult(self.path, self.frames_written, self._ring.overrun_frames, self.error)

    @property
    def overrun_frames(self) -> int:
        return self._ring.overrun_frames

    def _drain(self) -> int:
        data = self._ring.read()
        if len(data):
            np.clip(data, -1.0, 1.0, out=data)
            self._file.write(data)
            self.frames_written += len(data)
        return len(data)

    def _sync(self) -> None:
        """Perbarui ukuran di header WAV lalu paksa data ke disk."""
        sf._snd.sf_command(self._file._file, _SFC_UPDATE_HEADER_NOW, sf._ffi.NULL, 0)
        self._file.flush()

    def _writer_loop(self) -> None:
        last_sync = time.monotonic()
        try:
            while not self._stop.is_set():
                wrote = self._drain()
                if time.monotonic() - last_sync >= self._flush_interval:
                    self._sync()
                    last_sync = time.monotonic()
                if not wrote:
                    self._stop.wait(0.05)
        except Exception as exc:  # noqa: BLE001
            self._accepting = False
            self.error = f"Gagal menulis rekaman ke disk: {exc}"


@dataclass(frozen=True)
class DiskSpace:
    free_bytes: int
    ok: bool
    message: str


def check_free_space(folder: Path, minimum: int = MIN_FREE_BYTES) -> DiskSpace:
    """Cek sisa ruang disk; ok=False (dengan pesan peringatan) jika kurang dari 2 GB."""
    folder = Path(folder)
    probe = folder
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    free = shutil.disk_usage(probe).free
    if free < minimum:
        gb = free / 1024**3
        return DiskSpace(free, False,
                         f"Sisa ruang disk tinggal {gb:.1f} GB (kurang dari 2 GB). Rekaman bisa "
                         "terhenti jika disk penuh. Kosongkan ruang disk sebelum merekam.")
    return DiskSpace(free, True, "")
