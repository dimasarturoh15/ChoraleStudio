"""Pengukuran kelantangan sesuai ITU-R BS.1770-4 / EBU R128.

- LUFS terintegrasi: pyloudnorm.
- True Peak: oversampling 4x (polyphase FIR), diproses per potongan agar hemat RAM.
- LRA: EBU Tech 3342, dibuat sendiri (short-term 3 s tiap 0,1 s, gerbang -70 LUFS
  absolut dan -20 LU relatif, LRA = persentil 95 - persentil 10).
- Verifikasi silang dengan filter ebur128 milik FFmpeg (imageio-ffmpeg).
"""

from __future__ import annotations

import math
import os
import re
import subprocess
import tempfile
import warnings
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pyloudnorm
import soundfile as sf
from scipy import signal

SAMPLE_RATE = 48000
OVERSAMPLE = 4
CROSS_CHECK_TOLERANCE = 0.2

# Filter K-weighting BS.1770 untuk 48 kHz (tahap shelf + tahap high-pass RLB).
_K_SHELF = ([1.53512485958697, -2.69169618940638, 1.19839281085285], [1.0, -1.69065929318241, 0.73248077421585])
_K_HIGHPASS = ([1.0, -2.0, 1.0], [1.0, -1.99004745483398, 0.99007225036621])


def _as_2d(audio: np.ndarray) -> np.ndarray:
    return audio[:, None] if audio.ndim == 1 else audio


def integrated_lufs(audio: np.ndarray, samplerate: int = SAMPLE_RATE) -> float:
    """LUFS terintegrasi. -inf untuk hening atau audio < 0,4 detik."""
    if len(audio) < int(0.4 * samplerate):
        return -math.inf
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return float(pyloudnorm.Meter(samplerate).integrated_loudness(np.asarray(audio, dtype=np.float64)))


def _interpolation_phases(factor: int = OVERSAMPLE, taps_per_phase: int = 16) -> tuple[np.ndarray, int]:
    """Filter interpolasi Nyquist (sinc berjendela Kaiser, panjang ganjil) per fase.

    Karena cutoff = 1/factor dan panjang ganjil, fase 0 persis sama dengan sampel
    asli (tertunda), jadi hanya fase 1..factor-1 yang perlu dihitung.
    """
    h = signal.firwin(factor * taps_per_phase + 1, 1.0 / factor, window=("kaiser", 6.0)) * factor
    center = (len(h) - 1) // 2
    phases = [np.ascontiguousarray(h[k::factor], dtype=np.float32) for k in range(1, factor)]
    return phases, center // factor


_PHASES, _PHASE_DELAY = _interpolation_phases()


def oversampled_peaks(audio: np.ndarray) -> np.ndarray:
    """Puncak absolut hasil oversampling 4x per sampel asli (gabungan semua kanal), shape (frames,).

    Interpolasi polyphase: tiap fase adalah FIR pendek pada laju asli, jadi tidak
    perlu membentuk sinyal 4x lebih panjang. Nilai di sampel n adalah puncak dari
    sampel n dan tiga titik sisipan sesudahnya.
    """
    x = _as_2d(audio).astype(np.float32, copy=False)
    n = len(x)
    peak = np.abs(x[:, 0])
    for ch in range(1, x.shape[1]):
        np.maximum(peak, np.abs(x[:, ch]), out=peak)

    def phase_peak(job: tuple[int, np.ndarray]) -> np.ndarray:
        ch, phase = job
        y = np.convolve(x[:, ch], phase)[_PHASE_DELAY:_PHASE_DELAY + n]
        return np.abs(y, out=y)

    jobs = [(ch, phase) for ch in range(x.shape[1]) for phase in _PHASES]
    with ThreadPoolExecutor(max_workers=min(len(jobs), os.cpu_count() or 1)) as pool:
        for y in pool.map(phase_peak, jobs):
            np.maximum(peak, y, out=peak)
    return peak


def true_peak_db(audio: np.ndarray) -> float:
    """True Peak dalam dBTP (oversampling 4x)."""
    if len(audio) == 0:
        return -math.inf
    peak = float(oversampled_peaks(audio).max())
    return 20 * math.log10(peak) if peak > 0 else -math.inf


_K_SOS = np.array([_K_SHELF[0] + _K_SHELF[1], _K_HIGHPASS[0] + _K_HIGHPASS[1]])


def _k_weighted_power(audio: np.ndarray) -> np.ndarray:
    """Daya K-weighted dijumlahkan antar-kanal (bobot 1 untuk L/R/mono), float64."""
    x = _as_2d(audio).astype(np.float32, copy=False)
    y = signal.sosfilt(_K_SOS.astype(np.float32), x, axis=0)
    np.square(y, out=y)
    return y.sum(axis=1, dtype=np.float64)


def _block_means(power: np.ndarray, samplerate: int, blocks_per_window: int) -> np.ndarray:
    """Rata-rata daya per jendela (kelipatan 100 ms) yang bergeser tiap 100 ms."""
    hop = samplerate // 10
    nblocks = len(power) // hop
    if nblocks < blocks_per_window:
        return np.array([])
    sub = power[:nblocks * hop].reshape(nblocks, hop).mean(axis=1)
    return np.convolve(sub, np.ones(blocks_per_window) / blocks_per_window, mode="valid")


def fast_integrated_lufs(audio: np.ndarray, samplerate: int = SAMPLE_RATE) -> float:
    """LUFS terintegrasi BS.1770-4 versi cepat (blok 400 ms tiap 100 ms, gerbang -70 dan -10 LU).

    Dipakai berulang saat mencari gain mastering; nilai akhir di laporan memakai pyloudnorm.
    """
    blocks = _block_means(_k_weighted_power(audio), samplerate, 4)
    if len(blocks) == 0:
        return -math.inf
    with np.errstate(divide="ignore"):
        loud = -0.691 + 10 * np.log10(blocks)
    gated = blocks[loud > -70.0]
    if len(gated) == 0:
        return -math.inf
    relative = -0.691 + 10 * np.log10(gated.mean()) - 10.0
    final = gated[-0.691 + 10 * np.log10(gated) > relative]
    return float(-0.691 + 10 * np.log10(final.mean()))


def short_term_loudness(audio: np.ndarray, samplerate: int = SAMPLE_RATE) -> np.ndarray:
    """Short-term loudness (jendela 3 s) setiap 0,1 s, dalam LUFS."""
    window = _block_means(_k_weighted_power(audio), samplerate, 30)
    if len(window) == 0:
        return np.array([])
    with np.errstate(divide="ignore"):
        return -0.691 + 10 * np.log10(window)


def loudness_range(audio: np.ndarray, samplerate: int = SAMPLE_RATE) -> float:
    """LRA menurut EBU Tech 3342, dalam LU."""
    st = short_term_loudness(audio, samplerate)
    st = st[st > -70.0]
    if len(st) == 0:
        return 0.0
    relative_gate = 10 * np.log10(np.mean(10 ** (st / 10))) - 20.0
    st = st[st > relative_gate]
    if len(st) == 0:
        return 0.0
    p10, p95 = np.percentile(st, [10, 95])
    return float(p95 - p10)


@dataclass(frozen=True)
class Loudness:
    integrated_lufs: float
    true_peak_dbtp: float
    lra_lu: float


def measure(audio: np.ndarray, samplerate: int = SAMPLE_RATE) -> Loudness:
    return Loudness(integrated_lufs(audio, samplerate), true_peak_db(audio), loudness_range(audio, samplerate))


# ----- verifikasi silang FFmpeg -----

def ffmpeg_exe() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _no_window() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def run_ffmpeg(args: list[str], cancel=None) -> tuple[int, bytes, bytes]:
    """Jalankan FFmpeg; jika `cancel` (fungsi/Event) menjadi True, proses dihentikan dan
    ProcessingCancelled dilempar. Mengembalikan (kode keluar, stdout, stderr)."""
    from chorale.dsp.errors import ProcessingCancelled

    is_cancelled = getattr(cancel, "is_set", cancel)
    proc = subprocess.Popen([ffmpeg_exe(), *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            creationflags=_no_window())
    while True:
        try:
            out, err = proc.communicate(timeout=0.1)
            return proc.returncode, out, err
        except subprocess.TimeoutExpired:
            if is_cancelled is not None and is_cancelled():
                proc.kill()
                proc.communicate()
                raise ProcessingCancelled("Pemrosesan dibatalkan.")


def ffmpeg_ebur128(path: Path, cancel=None) -> Loudness:
    """Ukur file dengan filter ebur128 FFmpeg (peak=true)."""
    code, _, err_bytes = run_ffmpeg(["-hide_banner", "-nostats", "-i", str(path),
                                     "-filter_complex", "ebur128=peak=true", "-f", "null", "-"], cancel)
    stderr = err_bytes.decode("utf-8", errors="replace")
    summary = stderr[stderr.rfind("Summary:"):]
    if code != 0 or not summary:
        raise RuntimeError(f"FFmpeg ebur128 gagal: {stderr[-500:]}")

    def grab(label: str) -> float:
        m = re.search(rf"{label}:\s+(-?inf|-?\d+(?:\.\d+)?)", summary)
        if not m:
            raise RuntimeError(f"Tidak menemukan '{label}' di keluaran FFmpeg")
        return float(m.group(1))

    return Loudness(grab("I"), grab("Peak"), grab("LRA"))


@dataclass(frozen=True)
class CrossCheck:
    ours: Loudness
    ffmpeg: Loudness

    @property
    def lufs_diff(self) -> float:
        return abs(self.ours.integrated_lufs - self.ffmpeg.integrated_lufs)

    @property
    def true_peak_diff(self) -> float:
        return abs(self.ours.true_peak_dbtp - self.ffmpeg.true_peak_dbtp)

    @property
    def lra_diff(self) -> float:
        return abs(self.ours.lra_lu - self.ffmpeg.lra_lu)

    @property
    def ok(self) -> bool:
        return max(self.lufs_diff, self.true_peak_diff) <= CROSS_CHECK_TOLERANCE


def cross_check(audio: np.ndarray, samplerate: int = SAMPLE_RATE, ours: Loudness | None = None) -> CrossCheck:
    """Bandingkan pengukuran kita dengan FFmpeg ebur128 (audio ditulis ke file float sementara)."""
    ours = ours or measure(audio, samplerate)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "ukur.wav"
        sf.write(str(path), audio, samplerate, subtype="FLOAT")
        return CrossCheck(ours, ffmpeg_ebur128(path))
