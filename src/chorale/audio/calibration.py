"""Kalibrasi latensi round-trip: sinyal uji, deteksi jeda, dan simpan hasil.

Bagian ini murni numpy/scipy (tanpa perangkat audio) agar bisa dites.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

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
    from scipy import signal  # dimuat saat dibutuhkan (import scipy lambat)

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
    from scipy import signal

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


# ----- pengukuran dengan sound card (dipakai layar Pengaturan dan tools/calibrate_latency.py) -----

MIN_QUALITY = 20.0
ACCURATE_SPREAD = 1      # sampel: "Akurat"
ACCEPTABLE_SPREAD = 144  # sampel (3 ms): masih memenuhi PRD v1.1 rev. 1

SAFETY_STEPS = (
    "Kecilkan volume headphone ke nol atau lepas headphone dari kepala.",
    "Matikan phantom +48V di sound card.",
    "Sambungkan kabel dari Output sound card ke Input 1, dan kecilkan gain input.",
    "Matikan tombol direct monitor (OFF) agar suara input tidak ikut terdengar.",
)


class CalibrationError(Exception):
    """Kalibrasi gagal; pesan bisa langsung ditampilkan ke pengguna."""


class CalibrationCancelled(Exception):
    pass


def make_stimulus(samplerate: int = 48000) -> np.ndarray:
    """0,25 s hening + sweep 0,5 s + 1 s hening (cukup untuk latensi sampai ~1 s)."""
    sweep = make_sweep(samplerate)
    return np.concatenate([np.zeros(int(0.25 * samplerate), np.float32), sweep,
                           np.zeros(int(1.0 * samplerate), np.float32)])


def play_record_once(selection, stimulus: np.ndarray, blocksize: int) -> tuple[np.ndarray, float, int]:
    """Putar stimulus ke semua output sambil merekam semua input dalam satu stream.

    Kembalikan (rekaman, latensi laporan PortAudio dalam detik, jumlah blok bermasalah).
    """
    import time

    import sounddevice as sd

    from chorale.audio.device import open_duplex_stream

    total = len(stimulus)
    in_ch, out_ch = selection.input_channels, selection.output_channels
    play = np.repeat(stimulus[:, None], out_ch, axis=1).astype(np.float32)
    rec = np.zeros((total, in_ch), dtype=np.float32)
    pos = [0]
    flags = [0]

    def callback(indata, outdata, frames, t, status):
        if status:
            flags[0] += 1
        start = pos[0]
        n = min(frames, total - start)
        if n > 0:
            outdata[:n] = play[start:start + n]
            rec[start:start + n] = indata[:n]
        if n < frames:
            outdata[n:] = 0
        pos[0] = start + frames
        if pos[0] >= total:
            raise sd.CallbackStop

    stream = open_duplex_stream(selection, callback, blocksize)
    try:
        reported = sum(stream.latency)
        stream.start()
        deadline = time.monotonic() + total / 48000 + 3.0
        while stream.active:
            if time.monotonic() > deadline:
                raise CalibrationError("Sound card berhenti merespons saat kalibrasi. Cabut-colok lalu coba lagi.")
            time.sleep(0.02)
    finally:
        stream.close()
    return rec, reported, flags[0]


def measure_latency(selection, blocksize: int, runs: int = 5, progress=None, cancel=None,
                    samplerate: int = 48000) -> CalibrationResult:
    """Ukur latensi round-trip lewat kabel loopback, `runs` kali dengan stream baru tiap kali.

    progress(percobaan_ke, jumlah, jeda_sampel). cancel: fungsi/Event untuk membatalkan.
    Melempar CalibrationError jika sinyal uji tidak tertangkap.
    """
    from datetime import datetime

    is_cancelled = getattr(cancel, "is_set", cancel)
    stimulus = make_stimulus(samplerate)
    lags: list[int] = []
    reported_ms: list[float] = []
    for run in range(1, runs + 1):
        if is_cancelled is not None and is_cancelled():
            raise CalibrationCancelled()
        rec, reported, _ = play_record_once(selection, stimulus, blocksize)
        estimates = [estimate_delay(rec[:, c], stimulus) for c in range(rec.shape[1])]
        best = max(estimates, key=lambda e: e.quality)
        if best.quality < MIN_QUALITY:
            raise CalibrationError(
                "Sinyal uji tidak tertangkap. Pastikan kabel dari Output ke Input 1 terpasang, "
                "gain input tidak nol, dan sound card yang dipilih benar.")
        lags.append(best.lag_samples)
        reported_ms.append(reported * 1000)
        if progress:
            progress(run, runs, best.lag_samples)
    median = int(np.median(lags))
    return CalibrationResult(
        input_device=selection.input.name, output_device=selection.output.name,
        hostapi=selection.hostapi, exclusive=selection.exclusive, samplerate=samplerate,
        blocksize=blocksize, latency_samples=median, latency_ms=round(median / samplerate * 1000, 3),
        runs_samples=lags, spread_samples=max(lags) - min(lags),
        reported_latency_ms=round(float(np.mean(reported_ms)), 3),
        date=datetime.now().isoformat(timespec="seconds"),
    )


def accuracy_label(result: CalibrationResult) -> tuple[str, str]:
    """(teks, tingkat) untuk tampilan: tingkat 'baik', 'cukup', atau 'buruk'."""
    if result.spread_samples <= ACCURATE_SPREAD:
        return "Akurat", "baik"
    if result.spread_samples <= ACCEPTABLE_SPREAD:
        return "Cukup", "cukup"
    return "Tidak konsisten", "buruk"
