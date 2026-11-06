"""Mastering standar YouTube (PRD FR-7).

Urutan: kompresor bus ringan (1,5:1, reduksi maks 2 dB) -> gain menuju -14 LUFS
-> limiter true-peak (oversampling 4x, look-ahead 5 ms, ceiling -1,0 dBTP).

Prioritas:
  1. True Peak <= -1,0 dBTP: MUTLAK. Hasil akhir selalu diukur ulang; jika masih
     di atas ceiling, limiter diulang dengan ceiling lebih rendah, dan sebagai
     pengaman terakhir dipakai pengecilan statis.
  2. -14 LUFS +-1: diusahakan. Jika limiter harus menekan > 6 dB, gain dihentikan
     di level yang lebih pelan dan peringatan dicatat.
  3. LRA: hanya diukur.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.ndimage import minimum_filter1d, uniform_filter1d

from chorale.dsp.chain import compress
from chorale.dsp.measure import fast_integrated_lufs, integrated_lufs, loudness_range, oversampled_peaks

SAMPLE_RATE = 48000
from chorale.dsp.presets import CEILING_DBTP, LUFS_TOLERANCE, TARGET_LUFS  # noqa: E402,F401
LIMITER_MARGIN_DB = 0.15  # batas aman agar meter lain (mis. FFmpeg) juga membaca <= -1,0
MAX_LIMITER_REDUCTION_DB = 6.0
LOOKAHEAD_S = 0.005
RELEASE_S = 0.100
GAIN_BLOCK = 48

BUS_RATIO = 1.5
BUS_MAX_REDUCTION_DB = 2.0
BUS_ATTACK_S = 0.030
BUS_RELEASE_S = 0.250


def db_to_lin(db: float) -> float:
    return 10.0 ** (db / 20.0)


def _peak_db(peaks: np.ndarray) -> float:
    p = float(peaks.max()) if len(peaks) else 0.0
    return 20 * math.log10(p) if p > 0 else -math.inf


def limiter_gain_db(peaks: np.ndarray, ceiling_dbtp: float, input_gain_db: float = 0.0,
                    samplerate: int = SAMPLE_RATE) -> np.ndarray:
    """Kurva gain limiter (dB, <= 0) per sampel, stereo terhubung.

    peaks: puncak hasil oversampling 4x dari sinyal SEBELUM input_gain_db.
    Kurva dijamin <= kebutuhan di setiap sampel: minimum bergeser selebar
    look-ahead, pemulihan (release) eksponensial per blok 1 ms, lalu dihaluskan
    rata-rata bergerak selebar look-ahead (serangan berupa landaian, bukan loncatan).
    """
    n = len(peaks)
    if n == 0:
        return np.zeros(0)
    level = 20 * np.log10(np.maximum(peaks.astype(np.float64), 1e-12)) + input_gain_db
    need = np.minimum(0.0, ceiling_dbtp - level)
    if need.min() == 0.0:
        return np.zeros(n)
    la = int(LOOKAHEAD_S * samplerate)
    held = minimum_filter1d(need, size=2 * (la + GAIN_BLOCK) + 1, mode="nearest")

    nb = -(-n // GAIN_BLOCK)
    padded = np.zeros(nb * GAIN_BLOCK)
    padded[:n] = held
    blocks = padded.reshape(nb, GAIN_BLOCK).min(axis=1)
    decay = math.exp(-GAIN_BLOCK / (samplerate * RELEASE_S))
    curve = np.empty(nb)
    y = 0.0
    for i, b in enumerate(blocks.tolist()):
        y = min(b, y * decay)
        curve[i] = y
    stepped = np.repeat(curve, GAIN_BLOCK)[:n]
    return uniform_filter1d(stepped, size=2 * la + 1, mode="nearest")


def _apply(audio: np.ndarray, input_gain_db: float, curve_db: np.ndarray) -> np.ndarray:
    gain = (curve_db.astype(np.float32) + np.float32(input_gain_db)) * np.float32(math.log(10) / 20)
    np.exp(gain, out=gain)
    return audio.astype(np.float32, copy=False) * gain[:, None]


def limit(audio: np.ndarray, input_gain_db: float = 0.0, ceiling_dbtp: float = CEILING_DBTP,
          peaks: np.ndarray | None = None, samplerate: int = SAMPLE_RATE) -> tuple[np.ndarray, float, float]:
    """Beri gain lalu batasi True Peak. Kembalikan (audio, reduksi limiter maks dB, True Peak akhir).

    Ceiling dijamin: hasil diukur ulang dan diulang/dikecilkan bila perlu.
    """
    if peaks is None:
        peaks = oversampled_peaks(audio)
    target = ceiling_dbtp - LIMITER_MARGIN_DB
    curve = limiter_gain_db(peaks, target, input_gain_db, samplerate)
    out = _apply(audio, input_gain_db, curve)
    tp = _peak_db(oversampled_peaks(out))
    for _ in range(3):
        if tp <= ceiling_dbtp - 0.01:
            break
        target -= (tp - ceiling_dbtp) + 0.05
        curve = limiter_gain_db(peaks, target, input_gain_db, samplerate)
        out = _apply(audio, input_gain_db, curve)
        tp = _peak_db(oversampled_peaks(out))
    reduction = float(-curve.min()) if len(curve) else 0.0
    if tp > ceiling_dbtp - 0.01:  # pengaman terakhir: pengecilan statis
        trim = (ceiling_dbtp - 0.02) - tp
        out = (out * np.float32(db_to_lin(trim))).astype(np.float32)
        reduction -= trim
        tp += trim
    return out, reduction, tp


@dataclass
class MasterResult:
    audio: np.ndarray
    integrated_lufs: float
    true_peak_dbtp: float
    lra_lu: float
    gain_db: float
    bus_reduction_db: float
    limiter_reduction_db: float
    target_reached: bool
    warnings: list[str] = field(default_factory=list)


def master(mix: np.ndarray, samplerate: int = SAMPLE_RATE, progress=None) -> MasterResult:
    """Master campuran stereo menuju -14 LUFS dengan True Peak <= -1,0 dBTP.

    progress: fungsi opsional menerima persen 0-100 (dalam tahap mastering).
    """

    def report(pct: float) -> None:
        if progress:
            progress(pct)

    x, bus = compress(mix, samplerate, ratio=BUS_RATIO, attack_s=BUS_ATTACK_S,
                      release_s=BUS_RELEASE_S, max_reduction_db=BUS_MAX_REDUCTION_DB)
    report(10)
    start_lufs = fast_integrated_lufs(x, samplerate)
    if not math.isfinite(start_lufs):
        return MasterResult(x, start_lufs, _peak_db(oversampled_peaks(x)), 0.0, 0.0, 0.0, 0.0, False,
                            ["Campuran hening; mastering tidak dilakukan."])
    peaks = oversampled_peaks(x)  # dihitung sekali; dipakai ulang untuk setiap gain yang dicoba
    report(30)

    # Cari gain: -14 LUFS setelah limiter, tetapi reduksi limiter maks 6 dB.
    gain = TARGET_LUFS - start_lufs
    constrained = False
    target = CEILING_DBTP - LIMITER_MARGIN_DB
    for attempt in range(6):
        curve = limiter_gain_db(peaks, target, gain, samplerate)
        reduction = float(-curve.min())
        report(30 + 8 * (attempt + 1))
        if reduction > MAX_LIMITER_REDUCTION_DB + 0.05:
            gain -= reduction - MAX_LIMITER_REDUCTION_DB
            constrained = True
            continue
        if constrained:
            break
        error = TARGET_LUFS - fast_integrated_lufs(_apply(x, gain, curve), samplerate)
        if abs(error) <= 0.1:
            break
        gain += error

    out, reduction, tp = limit(x, gain, CEILING_DBTP, peaks, samplerate)
    report(85)
    lufs = integrated_lufs(out, samplerate)
    lra = loudness_range(out, samplerate)
    report(100)

    reached = abs(lufs - TARGET_LUFS) <= LUFS_TOLERANCE
    warnings: list[str] = []
    if not reached:
        reason = (" karena materinya sangat dinamis: untuk mencapai -14 LUFS limiter harus menekan "
                  f"lebih dari {MAX_LIMITER_REDUCTION_DB:g} dB, yang akan merusak dinamika lagu"
                  if constrained else "")
        warnings.append(f"Target -14 LUFS tidak tercapai. Master berhenti di {lufs:.1f} LUFS{reason}. "
                        "YouTube tidak akan mengecilkan lagu ini, hanya terdengar sedikit lebih pelan.")
    return MasterResult(out, lufs, tp, lra, gain, bus.max_reduction_db, reduction, reached, warnings)


def loudness_matched_gains(raw: np.ndarray, mastered: np.ndarray,
                           samplerate: int = SAMPLE_RATE) -> tuple[float, float]:
    """Gain (dB) untuk pemutar A/B agar Mentah dan Master sama kelantangannya.

    Yang lebih keras dikecilkan (tidak ada yang dikeraskan), agar tidak clip saat diputar.
    """
    a = integrated_lufs(raw, samplerate)
    b = integrated_lufs(mastered, samplerate)
    if not (math.isfinite(a) and math.isfinite(b)):
        return 0.0, 0.0
    level = min(a, b)
    return level - a, level - b
