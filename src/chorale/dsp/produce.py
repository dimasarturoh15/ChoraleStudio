"""Satu fungsi utama: proyek -> master WAV + MP3 + laporan (Segmen 4 + 5).

Progres dilaporkan dalam 7 langkah layar "Memproses Produksi":
  1 Membersihkan derau             5 Menata posisi stereo
  2 Menyaring frekuensi rendah     6 Menambahkan ruang (reverb)
  3 Merapikan karakter suara       7 Mastering standar YouTube
  4 Menyeimbangkan volume antar-suara
"""

from __future__ import annotations

import math
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

import numpy as np

from chorale.dsp.chain import ProcessingCancelled, ProductionResult, process_project
from chorale.dsp.export import (
    Mp3Info, base_name, encode_mp3, fmt_db, fmt_duration, trim_tail, write_wav,
)
from chorale.dsp.master import (
    CEILING_DBTP, LUFS_TOLERANCE, TARGET_LUFS, MasterResult, master,
)
from chorale.dsp.measure import CrossCheck, Loudness, fast_integrated_lufs, ffmpeg_ebur128
from chorale.dsp.reverb import REVERB_AMOUNT_LABELS, ROOM_PRESETS
from chorale.project.model import TRACK_LABELS

STEP_LABELS = {
    1: "Membersihkan derau",
    2: "Menyaring frekuensi rendah",
    3: "Merapikan karakter suara",
    4: "Menyeimbangkan volume antar-suara",
    5: "Menata posisi stereo",
    6: "Menambahkan ruang (reverb)",
    7: "Mastering standar YouTube",
}
# Tahap rantai FR-5 (1-7) -> langkah layar (1-6); langkah 7 = mastering + ekspor.
_CHAIN_TO_STEP = {1: 1, 2: 2, 3: 3, 4: 3, 5: 4, 6: 5, 7: 6}
_CHAIN_SHARE = 55.0  # persen progres untuk rantai pascaproduksi; sisanya mastering & ekspor

StepCallback = Callable[[int, float], None]


@dataclass
class ProduceResult:
    production: ProductionResult
    mastered: MasterResult
    raw: np.ndarray  # mixdown tanpa mastering, untuk A/B
    ab_gains_db: tuple[float, float]  # (gain Mentah, gain Master) agar kelantangan sama
    wav_path: Path | None = None
    mp3_path: Path | None = None
    report_path: Path | None = None
    mp3: Mp3Info | None = None
    verification: CrossCheck | None = None
    seconds: float = 0.0
    warnings: list[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return len(self.mastered.audio) / self.production.samplerate

    @property
    def youtube_ready(self) -> bool:
        return self.mastered.true_peak_dbtp <= CEILING_DBTP and self.mastered.target_reached


def produce(project, progress: StepCallback | None = None, cancel=None, export: bool = True,
            verify: bool = False, denoiser=None, when: datetime | None = None) -> ProduceResult:
    """Jalankan seluruh rantai: pascaproduksi -> mastering -> ekspor (WAV, MP3, laporan).

    progress(langkah 1-7, persen keseluruhan 0-100). cancel: fungsi/Event untuk membatalkan.
    verify: ukur ulang file WAV dengan FFmpeg ebur128 dan catat di laporan.
    """
    started = time.perf_counter()
    is_cancelled = getattr(cancel, "is_set", cancel)

    def check() -> None:
        if is_cancelled is not None and is_cancelled():
            raise ProcessingCancelled("Pemrosesan dibatalkan.")

    def chain_progress(stage: int, pct: float) -> None:
        if progress:
            progress(_CHAIN_TO_STEP[stage], pct * _CHAIN_SHARE / 100)

    def master_progress(pct: float) -> None:
        check()
        if progress:
            progress(7, _CHAIN_SHARE + pct * (85 - _CHAIN_SHARE) / 100)

    production = process_project(project, progress=chain_progress, cancel=cancel, denoiser=denoiser)
    check()
    mastered = master(production.mix, production.samplerate, progress=master_progress)
    mastered.audio = trim_tail(mastered.audio, production.samplerate)
    raw = trim_tail(production.mix, production.samplerate)
    check()
    raw_lufs = fast_integrated_lufs(raw, production.samplerate)
    level = min(raw_lufs, mastered.integrated_lufs)
    ab = (level - raw_lufs, level - mastered.integrated_lufs) if math.isfinite(level) else (0.0, 0.0)
    result = ProduceResult(production, mastered, raw, ab)
    result.warnings = list(mastered.warnings) + list(production.notes)

    if export:
        folder = project.master_dir
        folder.mkdir(exist_ok=True)
        stem = base_name(project.title, folder, when)
        result.wav_path = folder / f"{stem}_Master.wav"
        result.mp3_path = folder / f"{stem}_Master.mp3"
        result.report_path = folder / f"{stem}_Laporan.txt"
        outputs = (result.wav_path, result.mp3_path, result.report_path)
        try:
            write_wav(result.wav_path, mastered.audio, production.samplerate)
            if progress:
                progress(7, 90)
            check()
            # MP3 (encoder FFmpeg satu inti) dan verifikasi FFmpeg berjalan bersamaan.
            with ThreadPoolExecutor(max_workers=2) as pool:
                mp3_job = pool.submit(encode_mp3, result.wav_path, result.mp3_path, project.title, cancel=cancel)
                verify_job = pool.submit(ffmpeg_ebur128, result.wav_path, cancel) if verify else None
                result.mp3 = mp3_job.result()
                if verify_job is not None:
                    ours = Loudness(mastered.integrated_lufs, mastered.true_peak_dbtp, mastered.lra_lu)
                    result.verification = CrossCheck(ours, verify_job.result())
            check()
            if result.mp3.trim_db < 0:
                result.warnings.append(f"MP3 dikecilkan {-result.mp3.trim_db:.1f} dB agar puncaknya tetap ≤ -1,0 dBTP.")
            if result.verification is not None and not result.verification.ok:
                result.warnings.append("Pengukuran FFmpeg berbeda lebih dari 0,2 dari pengukuran aplikasi.")
            result.seconds = time.perf_counter() - started
            result.report_path.write_text(build_report(project, result, when), encoding="utf-8")
        except BaseException:
            # Nama dasar dijamin belum pernah dipakai, jadi file yang ada sekarang pasti buatan proses ini.
            for path in outputs:
                path.unlink(missing_ok=True)
            raise
    result.seconds = time.perf_counter() - started
    if progress:
        progress(7, 100)
    return result


def build_report(project, result: ProduceResult, when: datetime | None = None) -> str:
    """Laporan mastering berbahasa Indonesia."""
    m, p = result.mastered, result.production
    when = when or datetime.now()
    lines = [
        "LAPORAN MASTERING — HarmoniSATB Studio",
        "=" * 46,
        f"Judul lagu        : {project.title}",
        f"Dibuat            : {when.strftime('%d-%m-%Y %H:%M')}",
        f"Status            : {'Siap YouTube' if result.youtube_ready else 'Perlu perhatian (lihat peringatan)'}",
        "",
        "HASIL PENGUKURAN (ITU-R BS.1770-4 / EBU R128)",
        f"Kelantangan       : {fmt_db(m.integrated_lufs, 'LUFS')}   (target {fmt_db(TARGET_LUFS, 'LUFS')} ±{LUFS_TOLERANCE:g})",
        f"Puncak (True Peak): {fmt_db(m.true_peak_dbtp, 'dBTP')}   (batas {fmt_db(CEILING_DBTP, 'dBTP')})",
        f"Rentang dinamika  : {m.lra_lu:.1f} LU (LRA, hanya dilaporkan)",
        f"Durasi            : {fmt_duration(result.duration)}   (termasuk ekor reverb + 1 detik hening)",
        f"Reduksi limiter   : maks {m.limiter_reduction_db:.1f} dB",
        f"Kompresor bus     : maks {m.bus_reduction_db:.1f} dB",
        "",
        "PENGATURAN",
        f"Ruang             : {ROOM_PRESETS[p.room].label} · {REVERB_AMOUNT_LABELS[p.reverb_amount]} "
        f"(wet {p.wet * 100:.0f}%)",
        "Track yang diproses:",
    ]
    for tid, rep in p.tracks.items():
        track = project.tracks[tid]
        take = track.active_take
        lines.append(f"  - {TRACK_LABELS[tid]:<12} {take.label if take else '-':<16} "
                     f"volume {track.volume_db:+.1f} dB, peredam derau: {rep.denoise_note or '-'}")
    if result.mp3 is not None:
        lines += ["", "FILE",
                  f"  {result.wav_path.name}  (WAV 24-bit · 48 kHz · stereo, dither TPDF)",
                  f"  {result.mp3_path.name}  (MP3 320 kbps CBR, True Peak {fmt_db(result.mp3.true_peak_dbtp, 'dBTP')})",
                  f"  {result.report_path.name}"]
    if result.verification is not None:
        v = result.verification
        lines += ["", "VERIFIKASI INDEPENDEN (FFmpeg ebur128)",
                  f"  Kelantangan {fmt_db(v.ffmpeg.integrated_lufs, 'LUFS')} (selisih {v.lufs_diff:.2f} LU), "
                  f"True Peak {fmt_db(v.ffmpeg.true_peak_dbtp, 'dBTP')} (selisih {v.true_peak_diff:.2f} dB): "
                  f"{'cocok' if v.ok else 'BERBEDA'}"]
    lines += ["", "PERINGATAN DAN CATATAN"]
    lines += [f"  - {w}" for w in result.warnings] or ["  (tidak ada)"]
    lines += ["", f"Waktu proses: {result.seconds:.0f} detik", ""]
    return "\n".join(lines)
