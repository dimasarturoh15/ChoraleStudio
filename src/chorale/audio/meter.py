"""Level meter: puncak per blok dihitung di callback, dibaca UI dari thread lain."""

from __future__ import annotations

import numpy as np

CLIP_LEVEL = 0.999  # sekitar -0,01 dBFS
SILENCE_DB = -120.0
GREEN_FLOOR_DB = -42.0
YELLOW_FROM_DB = -12.0
RED_FROM_DB = -3.0


def to_dbfs(peak) -> np.ndarray:
    """Konversi puncak linear ke dBFS (hening = -120)."""
    peak = np.asarray(peak, dtype=np.float64)
    return np.maximum(20 * np.log10(np.maximum(peak, 1e-6)), SILENCE_DB)


def meter_zone(db: float) -> str:
    """Zona warna VU meter sesuai FR-1: 'kosong', 'hijau', 'kuning', 'merah'."""
    if db > RED_FROM_DB:
        return "merah"
    if db > YELLOW_FROM_DB:
        return "kuning"
    if db >= GREEN_FLOOR_DB:
        return "hijau"
    return "kosong"


class LevelMeter:
    """Simpan puncak tertinggi sejak dibaca terakhir, plus lampu clip yang tetap menyala.

    update() dipanggil dari callback audio; read()/clip()/reset_clip() dari
    thread UI. Lampu clip hanya dimatikan lewat reset_clip() (saat diklik).
    """

    def __init__(self, channels: int):
        self.channels = channels
        self._hold = np.zeros(channels, dtype=np.float32)
        self._clip = np.zeros(channels, dtype=bool)
        self._reset_requested = False

    def update(self, block: np.ndarray) -> None:
        if self._reset_requested:
            self._hold.fill(0.0)
            self._reset_requested = False
        if len(block) == 0:
            return
        peak = np.maximum(block.max(axis=0), -block.min(axis=0))
        np.maximum(self._hold, peak[: self.channels], out=self._hold)
        if peak.max() >= CLIP_LEVEL:
            self._clip |= peak[: self.channels] >= CLIP_LEVEL

    def read(self) -> np.ndarray:
        """Puncak linear per kanal sejak pembacaan terakhir, lalu reset penahan puncak."""
        value = self._hold.copy()
        self._reset_requested = True
        return value

    def read_db(self) -> np.ndarray:
        return to_dbfs(self.read())

    def clip(self) -> np.ndarray:
        return self._clip.copy()

    def reset_clip(self, channel: int | None = None) -> None:
        if channel is None:
            self._clip[:] = False
        else:
            self._clip[channel] = False
