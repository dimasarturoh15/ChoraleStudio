"""Tahap 5 (FR-6): penyeimbang level antar-track berbasis LUFS terintegrasi."""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass

import numpy as np
import pyloudnorm

VOCAL_TARGET_LUFS = -23.0
PIANO_TARGET_LUFS = -25.0  # 2 LU di bawah vokal agar vokal tetap di depan


def target_lufs(track_id: str) -> float:
    return PIANO_TARGET_LUFS if track_id == "piano" else VOCAL_TARGET_LUFS


def measure_lufs(audio: np.ndarray, samplerate: int = 48000) -> float:
    """LUFS terintegrasi (ITU-R BS.1770-4). -inf untuk hening atau audio < 0,4 detik."""
    if len(audio) < int(0.4 * samplerate):
        return -math.inf
    meter = pyloudnorm.Meter(samplerate)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return float(meter.integrated_loudness(np.asarray(audio, dtype=np.float64)))


@dataclass(frozen=True)
class BalanceInfo:
    measured_lufs: float
    target_lufs: float
    auto_gain_db: float
    offset_db: float

    @property
    def total_gain_db(self) -> float:
        return self.auto_gain_db + self.offset_db


def balance_stem(audio: np.ndarray, track_id: str, offset_db: float = 0.0,
                 samplerate: int = 48000) -> tuple[np.ndarray, BalanceInfo]:
    """Samakan stem ke target LUFS-nya, lalu tambahkan offset slider volume track."""
    measured = measure_lufs(audio, samplerate)
    target = target_lufs(track_id)
    auto = 0.0 if not math.isfinite(measured) else target - measured
    info = BalanceInfo(measured, target, auto, offset_db)
    gain = np.float32(10 ** (info.total_gain_db / 20))
    return (audio * gain).astype(np.float32), info
