"""Tahap 7: reverb konvolusi dengan impulse response (IR) sintetis.

IR dibuat oleh kode (bukan file rekaman), sehingga bebas masalah lisensi:
derau acak kiri/kanan yang tidak berkorelasi, diredam di atas 5 kHz, dengan
peluruhan eksponensial yang turun 60 dB tepat pada waktu decay preset, didahului
pre-delay 32 ms. Seed tetap, jadi IR selalu sama untuk preset yang sama.
"""

from __future__ import annotations

import numpy as np
from scipy import signal

SAMPLE_RATE = 48000
PRE_DELAY_S = 0.032
DAMPING_HZ = 5000.0


from chorale.dsp.presets import (  # noqa: E402,F401  (diekspor ulang)
    DEFAULT_AMOUNT, DEFAULT_ROOM, REVERB_AMOUNT_LABELS, REVERB_AMOUNTS, ROOM_PRESETS, RoomPreset,
)


def make_ir(decay_s: float, samplerate: int = SAMPLE_RATE, pre_delay_s: float = PRE_DELAY_S,
            damping_hz: float = DAMPING_HZ, seed: int = 2026) -> np.ndarray:
    """IR stereo (frames, 2) float32; energi tiap kanal dinormalkan ke 1."""
    rng = np.random.default_rng(seed)
    n_tail = int(round(decay_s * samplerate))
    noise = rng.standard_normal((n_tail, 2))
    sos = signal.butter(2, damping_hz, "lowpass", fs=samplerate, output="sos")
    noise = signal.sosfilt(sos, noise, axis=0)
    t = np.arange(n_tail) / samplerate
    envelope = 10.0 ** (-3.0 * t / decay_s)  # -60 dB pada t = decay_s
    fade_in = np.minimum(t / 0.003, 1.0)
    tail = noise * (envelope * fade_in)[:, None]
    tail /= np.sqrt(np.sum(tail**2, axis=0, keepdims=True))
    pre = np.zeros((int(round(pre_delay_s * samplerate)), 2))
    return np.concatenate([pre, tail]).astype(np.float32)


def ir_for_preset(room: str, samplerate: int = SAMPLE_RATE) -> np.ndarray:
    if room not in ROOM_PRESETS:
        raise ValueError(f"Preset ruang tidak dikenal: {room}")
    return make_ir(ROOM_PRESETS[room].decay_s, samplerate)


def convolve_stereo(dry: np.ndarray, ir: np.ndarray) -> np.ndarray:
    """Konvolusi kiri dengan IR kiri dan kanan dengan IR kanan; hasil memuat ekor penuh."""
    out = np.empty((len(dry) + len(ir) - 1, 2), dtype=np.float32)
    for ch in range(2):
        out[:, ch] = signal.oaconvolve(dry[:, ch], ir[:, ch], mode="full")
    return out


def decay_time_t30(ir_channel: np.ndarray, samplerate: int = SAMPLE_RATE) -> float:
    """Ukur RT60 dari IR (metode Schroeder, kemiringan -5 s.d. -35 dB dikali 2)."""
    energy = np.cumsum(ir_channel[::-1].astype(np.float64) ** 2)[::-1]
    edc = 10 * np.log10(energy / energy[0] + 1e-30)
    i5 = int(np.argmax(edc <= -5.0))
    i35 = int(np.argmax(edc <= -35.0))
    return 2.0 * (i35 - i5) / samplerate
