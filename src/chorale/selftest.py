"""Uji mandiri untuk teknisi: `HarmoniSATB Studio.exe --uji-mandiri`.

Membuat proyek sementara berisi 5 track sintetis (± 12 detik), menjalankan
produce() sampai ekspor, lalu memeriksa 3 file hasil dan target mastering.
Hasil ditulis ke log; kode keluar 0 = lulus. Tidak membutuhkan sound card.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import time
from pathlib import Path

import numpy as np

log = logging.getLogger("chorale.selftest")

SR = 48000
NOTES = {"piano": (130.8, 164.8, 196.0), "bass": (98.0,), "tenor": (196.0,), "alto": (261.6,), "sopran": (329.6,)}


def _tone(freqs, seconds: float, channels: int, amp: float) -> np.ndarray:
    t = np.arange(int(seconds * SR)) / SR
    x = sum(np.sin(2 * np.pi * f * t * (1 + 0.004 * np.sin(2 * np.pi * 5.5 * t))) for f in freqs)
    env = np.minimum(t / 0.1, 1.0) * np.minimum((seconds - t) / 0.3, 1.0)
    x = amp * x / np.max(np.abs(x)) * env
    return np.repeat(x[:, None], channels, axis=1).astype(np.float32)


def run_selftest() -> int:
    import soundfile as sf

    from chorale.dsp.export import decode_audio
    from chorale.dsp.measure import true_peak_db
    from chorale.dsp.produce import produce
    from chorale.project import Take, create_project

    folder = Path(tempfile.mkdtemp(prefix="harmonisatb_uji_"))
    started = time.perf_counter()
    try:
        project = create_project(folder, "Uji Mandiri", count_in_bars=0)
        for tid, freqs in NOTES.items():
            number, path = project.next_take_path(tid)
            sf.write(str(path), _tone(freqs, 12.0, project.track(tid).channels, 0.3), SR, subtype="PCM_24")
            project.add_take(tid, Take(number, path.name, "2026-01-01T00:00:00", 12.0))
        result = produce(project, verify=True)
        files = [result.wav_path, result.mp3_path, result.report_path]
        problems = [f"file tidak ada: {p.name}" for p in files if not p.is_file()]
        info = sf.info(str(result.wav_path))
        if (info.samplerate, info.channels, info.subtype) != (SR, 2, "PCM_24"):
            problems.append(f"format WAV salah: {info}")
        if true_peak_db(decode_audio(result.mp3_path)) > -1.0:
            problems.append("True Peak MP3 di atas -1,0 dBTP")
        if result.mastered.true_peak_dbtp > -1.0:
            problems.append("True Peak WAV di atas -1,0 dBTP")
        if result.verification is None or not result.verification.ok:
            problems.append("verifikasi FFmpeg tidak cocok")
        seconds = time.perf_counter() - started
        if problems:
            log.error("Uji mandiri GAGAL (%.1f s): %s", seconds, "; ".join(problems))
            return 1
        log.info("Uji mandiri LULUS dalam %.1f s: %.2f LUFS, %.2f dBTP, 3 file valid", seconds,
                 result.mastered.integrated_lufs, result.mastered.true_peak_dbtp)
        return 0
    except Exception:  # noqa: BLE001
        log.exception("Uji mandiri GAGAL karena error")
        return 1
    finally:
        shutil.rmtree(folder, ignore_errors=True)
