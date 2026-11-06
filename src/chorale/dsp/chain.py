"""Rantai pascaproduksi otomatis (PRD FR-5 & FR-6).

Tahap per track vokal:
  1 Peredam derau (DeepFilterNet, opsional)   5 Penyeimbang level (FR-6)
  2 High-pass filter 12 dB/oktaf              6 Panning / lebar stereo
  3 EQ anti-boxiness -2 dB @ 400 Hz, Q 1,0    7 Reverb konvolusi (bus kirim)
  4 Kompresor 2,5:1, 25/140 ms, reduksi maks 4 dB
Piano melewati tahap 2, 5, 6, dan 7. Tahap 5 berlaku untuk piano karena FR-6
menetapkan piano di -25 LUFS.

Bisa dijalankan tanpa UI. Fungsi pemrosesan menerima callback progres
(nomor tahap 1-7, persen keseluruhan 0-100) dan bisa dibatalkan.
"""

from __future__ import annotations

import math
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
from pedalboard import PeakFilter, Pedalboard
from scipy import signal

from chorale.dsp import denoise as denoise_module
from chorale.dsp.balance import BalanceInfo, balance_stem
from chorale.dsp.mixdown import mixdown
from chorale.dsp.reverb import REVERB_AMOUNTS, ROOM_PRESETS, ir_for_preset
from chorale.dsp.stereo import place_track

SAMPLE_RATE = 48000

STAGE_NAMES = {
    1: "Peredam derau",
    2: "High-pass filter",
    3: "EQ anti-boxiness",
    4: "Kompresor",
    5: "Penyeimbang level",
    6: "Panning",
    7: "Reverb",
}
VOCAL_STAGES = (1, 2, 3, 4, 5, 6, 7)
PIANO_STAGES = (2, 5, 6, 7)

HPF_CUTOFF_HZ = {"piano": 35.0, "bass": 75.0, "tenor": 75.0, "alto": 90.0, "sopran": 90.0}
HPF_ORDER = 2  # Butterworth orde 2 = 12 dB/oktaf

EQ_FREQ_HZ = 400.0
EQ_GAIN_DB = -2.0
EQ_Q = 1.0

COMP_RATIO = 2.5
COMP_ATTACK_S = 0.025
COMP_RELEASE_S = 0.140
COMP_MAX_REDUCTION_DB = 4.0
COMP_REFERENCE_PERCENTILE = 99.5
COMP_DETECTOR_BLOCK = 48  # 1 ms

ProgressCallback = Callable[[int, float], None]


class ProcessingCancelled(Exception):
    """Pemrosesan dibatalkan pengguna."""


# ----- tahap 2-4 -----

def highpass(audio: np.ndarray, track_id: str, samplerate: int = SAMPLE_RATE) -> np.ndarray:
    sos = signal.butter(HPF_ORDER, HPF_CUTOFF_HZ[track_id], "highpass", fs=samplerate, output="sos")
    return signal.sosfilt(sos, audio, axis=0).astype(np.float32)


def anti_boxiness(audio: np.ndarray, samplerate: int = SAMPLE_RATE) -> np.ndarray:
    board = Pedalboard([PeakFilter(cutoff_frequency_hz=EQ_FREQ_HZ, gain_db=EQ_GAIN_DB, q=EQ_Q)])
    out = board(np.ascontiguousarray(audio.T, dtype=np.float32), samplerate)
    return np.ascontiguousarray(out.T)


@dataclass(frozen=True)
class CompressorInfo:
    threshold_db: float
    max_reduction_db: float
    mean_reduction_db: float


def compress(audio: np.ndarray, samplerate: int = SAMPLE_RATE, ratio: float = COMP_RATIO,
             attack_s: float = COMP_ATTACK_S, release_s: float = COMP_RELEASE_S,
             max_reduction_db: float = COMP_MAX_REDUCTION_DB) -> tuple[np.ndarray, CompressorInfo]:
    """Kompresor feed-forward dengan threshold otomatis.

    Detektor: puncak per 1 ms, dihaluskan attack/release di domain dB. Threshold
    dipilih agar bagian terkeras track (persentil 99,5 level aktif) mendapat
    reduksi tepat 4 dB; reduksi juga dibatasi keras di 4 dB untuk lonjakan sesaat.
    """
    x = audio if audio.ndim == 2 else audio[:, None]
    n = len(x)
    if n == 0:
        return audio.copy(), CompressorInfo(0.0, 0.0, 0.0)
    block = COMP_DETECTOR_BLOCK
    nb = -(-n // block)
    det = np.zeros(nb * block, dtype=np.float32)
    det[:n] = np.max(np.abs(x), axis=1)
    level = 20 * np.log10(np.maximum(det.reshape(nb, block).max(axis=1), 1e-9))

    a_att = math.exp(-block / (samplerate * attack_s))
    a_rel = math.exp(-block / (samplerate * release_s))
    env = np.empty(nb)
    y = -120.0
    for i, v in enumerate(level.tolist()):
        coef = a_att if v > y else a_rel
        y = coef * y + (1.0 - coef) * v
        env[i] = y

    active = env > -60.0
    if not active.any():
        return audio.copy(), CompressorInfo(0.0, 0.0, 0.0)
    reference = np.percentile(env[active], COMP_REFERENCE_PERCENTILE)
    slope = 1.0 - 1.0 / ratio
    threshold = float(reference - max_reduction_db / slope)
    reduction = np.clip((env - threshold) * slope, 0.0, max_reduction_db)

    centers = (np.arange(nb) + 0.5) * block
    gain_db = np.interp(np.arange(n), centers, -reduction)
    out = (x * (10.0 ** (gain_db / 20.0))[:, None]).astype(np.float32)
    info = CompressorInfo(threshold, float(reduction.max()),
                          float(reduction[active].mean()) if active.any() else 0.0)
    return (out if audio.ndim == 2 else out[:, 0]), info


# ----- orkestrasi -----

@dataclass
class StemInput:
    track_id: str
    audio: np.ndarray  # (frames, kanal) float32
    volume_db: float = 0.0
    denoise: bool = True


@dataclass
class TrackReport:
    track_id: str
    stages: list[int] = field(default_factory=list)
    denoise_note: str = ""
    compressor: CompressorInfo | None = None
    balance: BalanceInfo | None = None


@dataclass
class ProductionResult:
    mix: np.ndarray  # (frames, 2) float32, termasuk ekor reverb
    samplerate: int
    room: str
    reverb_amount: str
    wet: float
    dry_frames: int
    tracks: dict[str, TrackReport]
    notes: list[str]
    excluded: list[str]

    @property
    def duration(self) -> float:
        return len(self.mix) / self.samplerate


class _Progress:
    """Hitung persen keseluruhan dari unit kerja yang sudah selesai."""

    def __init__(self, plan: list[tuple[int, float]], callback: ProgressCallback | None, cancel):
        self._total = sum(w for _, w in plan) or 1.0
        self._done = 0.0
        self._callback = callback
        self._cancel = getattr(cancel, "is_set", cancel)

    def check(self) -> None:
        if self._cancel is not None and self._cancel():
            raise ProcessingCancelled("Pemrosesan dibatalkan.")

    def begin(self, stage: int) -> None:
        self.check()
        if self._callback:
            self._callback(stage, 100.0 * self._done / self._total)

    def end(self, stage: int, weight: float) -> None:
        self._done += weight
        if self._callback:
            self._callback(stage, 100.0 * self._done / self._total)
        self.check()


_STAGE_WEIGHT = {1: 6.0, 2: 1.0, 3: 1.0, 4: 2.0, 5: 1.0, 6: 0.5}
_REVERB_WEIGHT = 4.0


def process_stems(stems: list[StemInput], room: str = "katedral", reverb_amount: str = "normal",
                  progress: ProgressCallback | None = None, cancel=None,
                  denoiser: Callable[[np.ndarray], np.ndarray] | None = None,
                  samplerate: int = SAMPLE_RATE) -> ProductionResult:
    """Proses stem mentah menjadi campuran stereo dengan ekor reverb.

    denoiser: fungsi audio mono -> audio mono. None = DeepFilterNet jika terpasang.
    cancel: callable tanpa argumen (atau threading.Event) yang bernilai True untuk membatalkan.
    """
    if room not in ROOM_PRESETS:
        raise ValueError(f"Preset ruang tidak dikenal: {room}")
    if reverb_amount not in REVERB_AMOUNTS:
        raise ValueError(f"Jumlah reverb tidak dikenal: {reverb_amount}")
    if not stems:
        raise ValueError("Tidak ada track terekam untuk diproses.")

    notes: list[str] = []
    if denoiser is None and any(s.track_id != "piano" and s.denoise for s in stems):
        if denoise_module.available():
            denoiser = denoise_module.denoise
        else:
            notes.append(denoise_module.MSG_UNAVAILABLE)

    reports = {s.track_id: TrackReport(s.track_id) for s in stems}

    def stages_for(s: StemInput) -> tuple[int, ...]:
        stages = PIANO_STAGES if s.track_id == "piano" else VOCAL_STAGES
        if 1 in stages and (not s.denoise or denoiser is None):
            stages = tuple(st for st in stages if st != 1)
        return stages

    plan = [(st, _STAGE_WEIGHT[st]) for st in range(1, 7) for s in stems if st in stages_for(s)]
    plan.append((7, _REVERB_WEIGHT))
    tracker = _Progress(plan, progress, cancel)

    audio = {s.track_id: np.ascontiguousarray(s.audio, dtype=np.float32) for s in stems}
    for s in stems:
        if s.track_id != "piano" and not s.denoise:
            reports[s.track_id].denoise_note = "dimatikan untuk track ini"

    def run_stage(stage: int, s: StemInput) -> np.ndarray:
        tid = s.track_id
        a = audio[tid]
        if stage == 1:
            a = np.column_stack([denoiser(a[:, c]) for c in range(a.shape[1])])
            reports[tid].denoise_note = "aktif (reduksi maks 12 dB)"
        elif stage == 2:
            a = highpass(a, tid, samplerate)
        elif stage == 3:
            a = anti_boxiness(a, samplerate)
        elif stage == 4:
            a, reports[tid].compressor = compress(a, samplerate)
        elif stage == 5:
            a, reports[tid].balance = balance_stem(a, tid, s.volume_db, samplerate)
        elif stage == 6:
            a = place_track(a, tid)
        return a.astype(np.float32, copy=False)

    # Track dalam satu tahap saling bebas, jadi diproses paralel (numpy/scipy melepas GIL).
    with ThreadPoolExecutor(max_workers=max(1, min(len(stems), os.cpu_count() or 1))) as pool:
        for stage in range(1, 7):
            todo = [s for s in stems if stage in stages_for(s)]
            if not todo:
                continue
            tracker.begin(stage)
            futures = {pool.submit(run_stage, stage, s): s.track_id for s in todo}
            for future in as_completed(futures):
                tid = futures[future]
                audio[tid] = future.result()
                reports[tid].stages.append(stage)
                tracker.end(stage, _STAGE_WEIGHT[stage])

    tracker.begin(7)
    wet = REVERB_AMOUNTS[reverb_amount]
    mix = mixdown(audio, ir_for_preset(room, samplerate), wet)
    for r in reports.values():
        r.stages.append(7)
    tracker.end(7, _REVERB_WEIGHT)

    dry_frames = max(len(a) for a in audio.values())
    return ProductionResult(mix, samplerate, room, reverb_amount, wet, dry_frames, reports, notes, [])


def project_stems(project) -> tuple[list[StemInput], list[str]]:
    """Ambil take aktif yang terdengar (aturan solo/mute sama dengan monitoring)."""
    from chorale.audio.player import audible_tracks, load_take_audio, TrackAudio

    candidates = []
    for track in project.tracks.values():
        take = track.active_take
        if take is None or not project.take_path(take).is_file():
            continue
        candidates.append(TrackAudio(track.id, np.empty((0, 1), np.float32), track.volume_db,
                                     track.solo, track.mute))
    audible = {t.track_id for t in audible_tracks(candidates)}
    excluded = [t.track_id for t in candidates if t.track_id not in audible]
    stems = []
    for track in project.tracks.values():
        if track.id in audible:
            stems.append(StemInput(track.id, load_take_audio(project.take_path(track.active_take)),
                                   track.volume_db, track.denoise))
    return stems, excluded


def process_project(project, progress: ProgressCallback | None = None, cancel=None,
                    denoiser=None) -> ProductionResult:
    """Proses take aktif proyek dengan preset ruang dan jumlah reverb proyek."""
    stems, excluded = project_stems(project)
    result = process_stems(stems, project.room_preset, project.reverb_amount,
                           progress=progress, cancel=cancel, denoiser=denoiser)
    result.excluded = excluded
    if excluded:
        from chorale.project.model import TRACK_LABELS
        names = ", ".join(TRACK_LABELS[t] for t in excluded)
        result.notes.append(f"Track tidak ikut diproses karena di-mute/tidak di-solo: {names}.")
    return result
