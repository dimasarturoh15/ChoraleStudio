"""Waveform dari audio asli: peak dihitung sekali per file (di thread), lalu disimpan di cache.

Peak yang sama dipakai meter track saat memutar, jadi file tidak pernah dibaca
ulang selama layar diperbarui.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import soundfile as sf
from PySide6.QtCore import QObject, QPointF, QRectF, QRunnable, QThreadPool, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from chorale.ui import theme
from chorale.ui.theme import COLORS

PEAK_RATE = 100           # titik peak per detik (blok 10 ms)
SAMPLES_PER_PEAK = 48000 // PEAK_RATE
DISPLAY_FLOOR_DB = -48.0  # tampilan memakai skala dB agar vokal pelan tetap terlihat


def compute_peaks(path: Path) -> np.ndarray:
    """Puncak absolut (semua kanal) per 10 ms, float32. Dibaca per potongan agar hemat RAM."""
    out: list[np.ndarray] = []
    rest = np.zeros(0, dtype=np.float32)
    for block in sf.blocks(str(path), blocksize=SAMPLES_PER_PEAK * 500, dtype="float32", always_2d=True):
        mono = np.concatenate([rest, np.abs(block).max(axis=1)])
        n = len(mono) // SAMPLES_PER_PEAK
        out.append(mono[:n * SAMPLES_PER_PEAK].reshape(n, SAMPLES_PER_PEAK).max(axis=1))
        rest = mono[n * SAMPLES_PER_PEAK:]
    if len(rest):
        out.append(np.array([rest.max()], dtype=np.float32))
    return np.concatenate(out) if out else np.zeros(0, dtype=np.float32)


def peaks_from_array(audio: np.ndarray) -> np.ndarray:
    """Seperti compute_peaks, tetapi dari audio di memori (mis. master hasil produce)."""
    mono = np.abs(audio).max(axis=1) if audio.ndim == 2 else np.abs(audio)
    n = len(mono) // SAMPLES_PER_PEAK
    peaks = mono[:n * SAMPLES_PER_PEAK].reshape(n, SAMPLES_PER_PEAK).max(axis=1)
    rest = mono[n * SAMPLES_PER_PEAK:]
    if len(rest):
        peaks = np.append(peaks, rest.max())
    return peaks.astype(np.float32)


def peak_at(peaks: np.ndarray | None, seconds: float, window: float = 1 / 30) -> float:
    """Puncak linear di jendela [seconds - window, seconds] (untuk meter saat memutar)."""
    if peaks is None or seconds < 0:
        return 0.0
    end = int(seconds * PEAK_RATE) + 1
    start = max(0, end - max(1, int(window * PEAK_RATE)))
    if start >= len(peaks):
        return 0.0
    return float(peaks[start:min(end, len(peaks))].max())


class _PeakJob(QRunnable):
    def __init__(self, key, path: Path, done):
        super().__init__()
        self.key, self.path, self.done = key, path, done

    def run(self):
        try:
            peaks = compute_peaks(self.path)
        except Exception:  # noqa: BLE001 - file rusak/hilang: tampilkan kosong
            peaks = np.zeros(0, dtype=np.float32)
        self.done.emit(self.key, peaks)


class PeakCache(QObject):
    """Cache peak per file (kunci: path + ukuran + waktu ubah). Penghitungan di QThreadPool."""

    ready = Signal(object, object)  # (path, peaks) - dipancarkan di thread UI
    _done = Signal(object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cache: dict[tuple, np.ndarray] = {}
        self._pending: set[tuple] = set()
        self._done.connect(self._store)

    @staticmethod
    def _key(path: Path) -> tuple:
        st = path.stat()
        return (str(path), st.st_size, st.st_mtime_ns)

    def get(self, path: Path) -> np.ndarray | None:
        """Peak yang sudah ada; jika belum, mulai hitung di latar dan kembalikan None."""
        try:
            key = self._key(path)
        except OSError:
            return None
        if key in self._cache:
            return self._cache[key]
        if key not in self._pending:
            self._pending.add(key)
            QThreadPool.globalInstance().start(_PeakJob(key, path, self._done))
        return None

    def get_blocking(self, path: Path) -> np.ndarray:
        key = self._key(path)
        if key not in self._cache:
            self._cache[key] = compute_peaks(path)
        return self._cache[key]

    def _store(self, key, peaks) -> None:
        self._pending.discard(key)
        self._cache[key] = peaks
        self.ready.emit(Path(key[0]), peaks)


def _display_level(peaks: np.ndarray) -> np.ndarray:
    db = 20 * np.log10(np.maximum(peaks, 1e-6))
    return np.clip((db - DISPLAY_FLOOR_DB) / -DISPLAY_FLOOR_DB, 0.0, 1.0)


class WaveformView(QWidget):
    """Gambar waveform satu track + playhead. Kolom piksel dihitung ulang hanya bila data/ukuran berubah."""

    seekRequested = Signal(float)

    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self.shade_played = False   # arsir bagian yang sudah diputar (layar Hasil)
        self.seekable = False       # klik untuk pindah posisi
        self.color = QColor(color)
        self.setMinimumHeight(80)
        self._peaks: np.ndarray | None = None
        self._live: np.ndarray | None = None
        self._live_len = 0
        self._view_seconds = 30.0
        self._playhead: float | None = None
        self._playhead_color = QColor("#FFFFFF")
        self._columns: np.ndarray | None = None
        self.placeholder = "Belum direkam"
        self.loading = False

    # ----- data -----
    def set_peaks(self, peaks: np.ndarray | None) -> None:
        self._peaks = peaks
        self._live = None
        self._live_len = 0
        self._columns = None
        self.update()

    def start_live(self) -> None:
        """Mulai waveform langsung dari meter input (saat merekam)."""
        self._peaks = None
        self._live = np.zeros(PEAK_RATE * 600, dtype=np.float32)
        self._live_len = 0
        self._columns = None
        self.update()

    def append_live(self, seconds: float, peak: float) -> None:
        if self._live is None or seconds < 0:
            return
        end = int(seconds * PEAK_RATE)
        if end >= len(self._live):
            grown = np.zeros(max(end + 1, 2 * len(self._live)), dtype=np.float32)
            grown[:len(self._live)] = self._live
            self._live = grown
        if end > self._live_len:
            self._live[self._live_len:end] = peak
            self._live_len = end
            self._columns = None
            self.update()

    def set_view_seconds(self, seconds: float) -> None:
        seconds = max(1.0, seconds)
        if abs(seconds - self._view_seconds) > 1e-6:
            self._view_seconds = seconds
            self._columns = None
            self.update()

    def set_playhead(self, seconds: float | None, color: str | None = None) -> None:
        if color:
            self._playhead_color = QColor(color)
        if seconds != self._playhead:
            self._playhead = seconds
            self.update()

    def mousePressEvent(self, event):
        if self.seekable and self.has_audio():
            inner_left, inner_width = 12.5, self.width() - 25.0
            frac = (event.position().x() - inner_left) / max(1.0, inner_width)
            self.seekRequested.emit(max(0.0, min(1.0, frac)) * self._view_seconds)
        super().mousePressEvent(event)

    def has_audio(self) -> bool:
        return (self._peaks is not None and len(self._peaks) > 0) or self._live is not None

    def resizeEvent(self, event):
        self._columns = None
        super().resizeEvent(event)

    def _compute_columns(self, width: int) -> np.ndarray:
        data = self._live[:self._live_len] if self._live is not None else self._peaks
        cols = np.zeros(width, dtype=np.float32)
        if data is None or len(data) == 0 or width <= 0:
            return cols
        per_px = self._view_seconds * PEAK_RATE / width
        edges = (np.arange(width + 1) * per_px).astype(np.int64)
        valid = edges[:-1] < len(data)
        idx = np.minimum(edges[:-1][valid], len(data) - 1)
        stop = np.minimum(np.maximum(edges[1:][valid], idx + 1), len(data))
        level = _display_level(data)
        maxima = np.maximum.reduceat(level, idx) if len(idx) else np.zeros(0)
        # reduceat mengambil sampai indeks berikutnya; kolom terakhir dipotong di 'stop'.
        if len(idx):
            maxima[-1] = level[idx[-1]:stop[-1]].max()
        cols[:len(maxima)] = maxima
        return cols

    # ----- gambar -----
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(COLORS["border"]), 1))
        p.setBrush(QColor(COLORS["app"]))
        p.drawRoundedRect(r, 6, 6)
        inner = r.adjusted(12, 10, -12, -10)
        mid = inner.center().y()
        if not self.has_audio():
            p.setPen(QColor(COLORS["text2"]))
            p.setFont(theme.font(16))
            p.drawText(r, Qt.AlignCenter, "Memuat waveform…" if self.loading else self.placeholder)
            p.end()
            return
        dash = QPen(QColor(COLORS["border"]), 1, Qt.DashLine)
        p.setPen(dash)
        p.drawLine(QPointF(inner.left(), mid), QPointF(inner.right(), mid))
        width = int(inner.width())
        if self._columns is None or len(self._columns) != width:
            self._columns = self._compute_columns(width)
        half = inner.height() / 2
        p.setPen(QPen(self.color, 1))
        x0 = inner.left()
        for x, a in enumerate(self._columns):
            if a > 0.0:
                h = max(0.5, float(a) * half)
                p.drawLine(QPointF(x0 + x, mid - h), QPointF(x0 + x, mid + h))
        if self._playhead is not None and self._playhead >= 0:
            x = x0 + min(1.0, self._playhead / self._view_seconds) * inner.width()
            if self.shade_played:
                shade = QColor(COLORS["blue"])
                shade.setAlphaF(0.12)
                p.fillRect(QRectF(inner.left(), r.top() + 1, x - inner.left(), r.height() - 2), shade)
            p.setPen(QPen(self._playhead_color, 2))
            p.drawLine(QPointF(x, r.top() + 2), QPointF(x, r.bottom() - 2))
        p.end()


def view_seconds_for(durations: list[float], position: float = 0.0) -> float:
    """Lebar garis waktu bersama: take terpanjang (atau posisi rekam), minimal 30 detik, +2%."""
    longest = max([d for d in durations if d] + [position, 30.0])
    return math.ceil(longest * 1.02)
