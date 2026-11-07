"""Penyejajaran take vokal memakai kanal acuan (kabel Output -> input yang tidak dipakai mikrofon).

Driver USB generik seperti pada SPL Audio SC202HD memulai setiap stream dengan latensi
yang berbeda (bisa beberapa milidetik) dan kadang menggesernya di tengah rekaman tanpa
melapor. Kalibrasi sekali pakai tidak bisa menangkap itu. Kanal acuan merekam apa yang
benar-benar keluar dari output pada saat yang sama dengan mikrofon, jadi setiap take
bisa mengukur latensinya sendiri.

Jika take direkam mulai frame lagu L_kal (latensi kalibrasi), sedangkan latensi
sebenarnya L, maka acuan[i] ~= diputar[i - e] dan isi take pada indeks i berasal dari
frame musik i - e, dengan e = L - L_kal. Take disejajarkan dengan mengambil
take[q + e] untuk frame musik q; e diukur per jendela sehingga lompatan di tengah
lagu ikut dikoreksi per segmen.

Hanya NumPy (tanpa SciPy) agar tidak memperlambat layar rekam.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

log = logging.getLogger("chorale.audio")

SAMPLE_RATE = 48000
WINDOW = SAMPLE_RATE           # panjang jendela ukur (1 detik)
HOP = SAMPLE_RATE // 2         # jarak antar-jendela (0,5 detik)
# Rentang pencarian +-100 ms: cukup untuk selisih kalibrasi/perkiraan driver, dan lebih kecil
# dari jarak ketukan tercepat (240 BPM = 250 ms) sehingga klik metronom tidak tertukar.
MAX_SHIFT = SAMPLE_RATE // 10
MIN_CORRELATION = 0.5          # korelasi ternormalisasi minimum agar jendela dipercaya
MIN_RMS = 10 ** (-60 / 20)     # jendela acuan yang lebih pelan dari -60 dBFS dilewati
# Perubahan lebih kecil dianggap derau pengukuran. Di SC202HD, klik bernada berbeda terukur
# selisih 11 sampel (tunda DAC/kabel/ADC bergantung frekuensi); lompatan driver nyata >= 65 sampel.
JUMP_TOLERANCE = 24            # sampel (0,5 ms)
FADE = 48                      # sampel (1 ms) fade di sambungan antar-segmen


@dataclass(frozen=True)
class Segment:
    start: int   # frame musik (indeks hasil) awal segmen
    offset: int  # e: geser take sebesar ini


@dataclass(frozen=True)
class AlignmentResult:
    segments: tuple[Segment, ...]
    windows: int        # jumlah jendela yang diukur
    valid_windows: int  # jendela dengan acuan yang jelas
    frames: int         # panjang take setelah disejajarkan

    @property
    def offset(self) -> int:
        return self.segments[0].offset

    @property
    def jumps(self) -> int:
        return len(self.segments) - 1


def _next_pow2(n: int) -> int:
    return 1 << (int(n) - 1).bit_length()


def measure_offsets(reference: np.ndarray, played: np.ndarray) -> list[tuple[int, int | None]]:
    """e per jendela: [(frame musik awal jendela, e atau None jika acuan tidak jelas)]."""
    reference = np.asarray(reference, dtype=np.float64)
    padded = np.concatenate([np.zeros(MAX_SHIFT), np.asarray(played, dtype=np.float64),
                             np.zeros(len(reference) + MAX_SHIFT + WINDOW)])
    span = WINDOW + 2 * MAX_SHIFT
    n_fft = _next_pow2(span + WINDOW)
    points: list[tuple[int, int | None]] = []
    for q in range(0, max(len(reference) - WINDOW, 0) + 1, HOP):
        r = reference[q:q + WINDOW]
        if len(r) < WINDOW or np.sqrt(np.mean(r * r)) < MIN_RMS:
            points.append((q, None))
            continue
        p = padded[q:q + span]  # frame diputar q - MAX_SHIFT ... q + WINDOW + MAX_SHIFT
        corr = np.fft.irfft(np.fft.rfft(p, n_fft) * np.conj(np.fft.rfft(r, n_fft)), n_fft)[:2 * MAX_SHIFT + 1]
        energy = np.concatenate([[0.0], np.cumsum(p * p)])
        window_energy = energy[WINDOW:WINDOW + 2 * MAX_SHIFT + 1] - energy[:2 * MAX_SHIFT + 1]
        ncc = corr / (np.sqrt(np.sum(r * r) * np.maximum(window_energy, 1e-20)))
        s = int(np.argmax(ncc))
        points.append((q, MAX_SHIFT - s if ncc[s] >= MIN_CORRELATION else None))
    return points


def build_segments(points: list[tuple[int, int | None]]) -> tuple[Segment, ...] | None:
    """Gabungkan ukuran per jendela menjadi segmen dengan e tetap; None jika tidak ada yang jelas."""
    valid = [(q, e) for q, e in points if e is not None]
    if not valid:
        return None
    values = np.array([e for _, e in valid])
    if len(values) >= 3:  # buang lonjakan tunggal (median 3 titik)
        padded = np.concatenate([values[:1], values, values[-1:]])
        values = np.median(np.stack([padded[:-2], padded[1:-1], padded[2:]]), axis=0).astype(int)
    segments: list[Segment] = []
    group: list[int] = []
    group_start = 0
    for (q, _), e in zip(valid, values):
        if group and abs(e - int(np.median(group))) > JUMP_TOLERANCE:
            segments.append(Segment(group_start, int(np.median(group))))
            group, group_start = [], q
        group.append(int(e))
    segments.append(Segment(group_start, int(np.median(group))))
    return tuple(segments)


def apply_segments(audio: np.ndarray, segments: tuple[Segment, ...]) -> np.ndarray:
    """Susun take baru: untuk tiap segmen ambil audio[q + e]; sambungan diberi fade 1 ms."""
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim == 1:
        audio = audio[:, None]
    n, ch = audio.shape
    total = max(n - segments[-1].offset, 0)
    out = np.zeros((total, ch), dtype=np.float32)
    bounds = [s.start for s in segments[1:]] + [total]
    for i, (seg, end) in enumerate(zip(segments, bounds)):
        start = 0 if i == 0 else seg.start
        end = min(end, total)
        if end <= start:
            continue
        src_lo, src_hi = start + seg.offset, end + seg.offset
        lo, hi = max(src_lo, 0), min(src_hi, n)
        if hi > lo:
            out[start + (lo - src_lo):start + (hi - src_lo)] = audio[lo:hi]
        if len(segments) > 1:
            fade = np.linspace(0.0, 1.0, min(FADE, (end - start) // 2), dtype=np.float32)[:, None]
            if i > 0 and len(fade):
                out[start:start + len(fade)] *= fade
            if i < len(segments) - 1 and len(fade):
                out[end - len(fade):end] *= fade[::-1]
    return out


def align_take(take_path: Path, reference_path: Path, played: np.ndarray) -> AlignmentResult | None:
    """Ukur e dari kanal acuan lalu tulis ulang take secara atomik. None = acuan tidak terdeteksi."""
    take_path, reference_path = Path(take_path), Path(reference_path)
    reference, _ = sf.read(str(reference_path), dtype="float32", always_2d=True)
    points = measure_offsets(reference[:, 0], played)
    segments = build_segments(points)
    valid = sum(e is not None for _, e in points)
    if segments is None:
        log.warning("Kanal acuan tidak terdeteksi untuk %s (%d jendela)", take_path.name, len(points))
        return None
    audio, sr = sf.read(str(take_path), dtype="float32", always_2d=True)
    aligned = apply_segments(audio, segments)
    tmp = take_path.with_name(take_path.stem + ".selaras.tmp")
    sf.write(str(tmp), aligned, sr, subtype="PCM_24", format="WAV")
    os.replace(tmp, take_path)
    result = AlignmentResult(segments, len(points), valid, len(aligned))
    log.info("Take %s disejajarkan dengan kanal acuan: geser %+d sampel, %d lompatan, %d/%d jendela jelas",
             take_path.name, result.offset, result.jumps, valid, len(points))
    return result


__all__ = ["AlignmentResult", "Segment", "align_take", "apply_segments", "build_segments", "measure_offsets"]
