"""Gabungkan track yang sudah ditempatkan di stereo, plus bus kirim reverb dengan ekor penuh."""

from __future__ import annotations

import numpy as np

from chorale.dsp.reverb import convolve_stereo


def sum_tracks(placed: dict[str, np.ndarray]) -> np.ndarray:
    """Jumlahkan track stereo (frames, 2) dengan panjang berbeda; yang pendek diisi hening."""
    length = max((len(a) for a in placed.values()), default=0)
    bus = np.zeros((length, 2), dtype=np.float32)
    for audio in placed.values():
        bus[:len(audio)] += audio
    return bus


def mixdown(placed: dict[str, np.ndarray], ir: np.ndarray, wet: float) -> np.ndarray:
    """Campuran akhir = (1 - wet) * dry + wet * reverb(dry); panjang = dry + ekor IR."""
    dry = sum_tracks(placed)
    if len(dry) == 0:
        return dry
    out = convolve_stereo(dry, ir)
    out *= np.float32(wet)
    out[:len(dry)] += dry * np.float32(1.0 - wet)
    return out
