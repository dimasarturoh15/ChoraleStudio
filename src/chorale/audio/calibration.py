"""Kalibrasi latensi round-trip: sinyal uji, deteksi jeda, dan simpan hasil.

Bagian ini murni numpy/scipy (tanpa perangkat audio) agar bisa dites.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
from scipy import signal

from chorale.appdirs import user_config_dir, write_json_atomic

CALIBRATION_FILE = "calibration.json"


def make_sweep(
    samplerate: int,
    duration: float = 0.5,
    f_start: float = 200.0,
    f_end: float = 16000.0,
    amplitude: float = 0.5,
) -> np.ndarray:
    """Sweep logaritmik pendek dengan fade 5 ms di kedua ujung (float32, mono)."""
    t = np.arange(int(round(duration * samplerate))) / samplerate
    sweep = signal.chirp(t, f0=f_start, t1=duration, f1=f_end, method="logarithmic")
    fade = int(0.005 * samplerate)
    ramp = np.sin(np.linspace(0.0, np.pi / 2, fade)) ** 2
    sweep[:fade] *= ramp
    sweep[-fade:] *= ramp[::-1]
    return (amplitude * sweep).astype(np.float32)


@dataclass(frozen=True)
class DelayEstimate:
    """Hasil deteksi jeda antara sinyal referensi dan rekaman."""

    lag_samples: int
    lag_fractional: float
    quality: float
    inverted: bool


def estimate_delay(recorded: np.ndarray, reference: np.ndarray) -> DelayEstimate:
    """Cari jeda rekaman terhadap referensi dengan cross-correlation.

    lag_samples: jeda bulat (sampel), lag_fractional: jeda dengan interpolasi
    parabola. quality: puncak korelasi dibagi median |korelasi| (makin besar
    makin yakin; di bawah ~20 berarti sinyal uji kemungkinan tidak tertangkap).
    inverted: True jika polaritas terbalik.
    """
    recorded = np.asarray(recorded, dtype=np.float64)
    reference = np.asarray(reference, dtype=np.float64)
    corr = signal.correlate(recorded, reference, mode="full", method="fft")
    lags = signal.correlation_lags(len(recorded), len(reference), mode="full")
    valid = lags >= 0
    corr, lags = corr[valid], lags[valid]
    magnitude = np.abs(corr)
    peak = int(np.argmax(magnitude))

    frac = 0.0
    if 0 < peak < len(magnitude) - 1:
        a, b, c = magnitude[peak - 1], magnitude[peak], magnitude[peak + 1]
        denom = a - 2 * b + c
        if denom != 0:
            frac = 0.5 * (a - c) / denom

    noise_floor = float(np.median(magnitude)) or 1e-12
    return DelayEstimate(
        lag_samples=int(lags[peak]),
        lag_fractional=float(lags[peak] + frac),
        quality=float(magnitude[peak] / noise_floor),
        inverted=bool(corr[peak] < 0),
    )


@dataclass
class CalibrationResult:
    """Hasil kalibrasi untuk satu kombinasi perangkat, host API, dan buffer."""

    input_device: str
    output_device: str
    hostapi: str
    exclusive: bool
    samplerate: int
    blocksize: int
    latency_samples: int
    latency_ms: float
    runs_samples: list[int] = field(default_factory=list)
    spread_samples: int = 0
    reported_latency_ms: float | None = None
    date: str = ""

    def key(self) -> tuple:
        return (self.input_device, self.output_device, self.hostapi, self.exclusive, self.samplerate, self.blocksize)


def default_calibration_path() -> Path:
    return user_config_dir() / CALIBRATION_FILE


def load_calibrations(path: Path | None = None) -> list[CalibrationResult]:
    """Baca semua hasil kalibrasi; daftar kosong jika file belum ada."""
    path = path or default_calibration_path()
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [CalibrationResult(**entry) for entry in data.get("entries", [])]


def save_calibration(result: CalibrationResult, path: Path | None = None) -> Path:
    """Simpan hasil; entri lama dengan kombinasi yang sama diganti."""
    path = path or default_calibration_path()
    entries = [e for e in load_calibrations(path) if e.key() != result.key()]
    entries.append(result)
    write_json_atomic(path, {"version": 1, "entries": [asdict(e) for e in entries]})
    return path


def find_calibration(input_device: str, output_device: str, hostapi: str, exclusive: bool,
                     blocksize: int, samplerate: int = 48000,
                     path: Path | None = None) -> CalibrationResult | None:
    """Cari hasil kalibrasi untuk kombinasi perangkat, mode, dan buffer yang persis sama."""
    key = (input_device, output_device, hostapi, exclusive, samplerate, blocksize)
    return next((e for e in load_calibrations(path) if e.key() == key), None)
