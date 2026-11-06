"""Tahap 6: panning constant-power (-3 dB di tengah) dan lebar stereo piano."""

from __future__ import annotations

import math

import numpy as np

# Posisi pan: -1 = kiri penuh, +1 = kanan penuh (PRD FR-5 tahap 6).
PAN_POSITIONS = {"tenor": -0.25, "sopran": -0.12, "bass": 0.12, "alto": 0.25, "piano": 0.0}
PIANO_WIDTH = 0.65


def pan_gains(position: float) -> tuple[float, float]:
    """Gain kiri/kanan constant-power: di tengah masing-masing cos(45°) = -3 dB."""
    theta = (position + 1.0) * math.pi / 4.0
    return math.cos(theta), math.sin(theta)


def pan_mono(audio: np.ndarray, position: float) -> np.ndarray:
    """Mono (frames,) -> stereo (frames, 2)."""
    gl, gr = pan_gains(position)
    mono = audio.reshape(-1)
    return np.column_stack([mono * gl, mono * gr]).astype(np.float32)


def stereo_width(audio: np.ndarray, width: float) -> np.ndarray:
    """Skala komponen side (M/S): width 1 = asli, 0 = mono."""
    mid = (audio[:, 0] + audio[:, 1]) * 0.5
    side = (audio[:, 0] - audio[:, 1]) * 0.5 * width
    return np.column_stack([mid + side, mid - side]).astype(np.float32)


def place_track(audio: np.ndarray, track_id: str) -> np.ndarray:
    """Tempatkan satu track di panggung stereo sesuai PRD."""
    if audio.ndim == 2 and audio.shape[1] == 2:
        return stereo_width(audio, PIANO_WIDTH if track_id == "piano" else 1.0)
    return pan_mono(audio, PAN_POSITIONS[track_id])
