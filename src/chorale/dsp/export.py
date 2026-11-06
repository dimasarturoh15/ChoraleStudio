"""Ekspor master (PRD FR-8): WAV 24-bit + dither TPDF, MP3 320 kbps CBR, laporan .txt.

Nama file: <Judul>_<YYYYMMDD-HHMM>_Master.wav / _Master.mp3 / _Laporan.txt di
folder master/ proyek. Ketiganya selalu memakai nama dasar yang sama, dan tidak
pernah menimpa file yang sudah ada.
"""

from __future__ import annotations

import math
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import soundfile as sf

from chorale.dsp.measure import _no_window, ffmpeg_exe, true_peak_db

SAMPLE_RATE = 48000
TAIL_FLOOR_DB = -60.0
TAIL_SILENCE_S = 1.0
MP3_BITRATE = "320k"
CEILING_DBTP = -1.0
_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def clean_title(title: str) -> str:
    """Judul -> bagian nama file: tanpa karakter terlarang Windows, spasi menjadi garis bawah."""
    name = _FORBIDDEN.sub("", title)
    name = re.sub(r"\s+", "_", name.strip()).strip("._")
    return name[:80] or "Lagu"


def base_name(title: str, folder: Path, when: datetime | None = None) -> str:
    """Nama dasar <Judul>_<YYYYMMDD-HHMM> yang belum dipakai oleh ketiga file ekspor."""
    stem = f"{clean_title(title)}_{(when or datetime.now()).strftime('%Y%m%d-%H%M')}"
    candidate, n = stem, 2
    while any((folder / f"{candidate}{suffix}").exists()
              for suffix in ("_Master.wav", "_Master.mp3", "_Laporan.txt")):
        candidate = f"{stem}-{n}"
        n += 1
    return candidate


def trim_tail(audio: np.ndarray, samplerate: int = SAMPLE_RATE, floor_db: float = TAIL_FLOOR_DB,
              silence_s: float = TAIL_SILENCE_S) -> np.ndarray:
    """Potong setelah sampel terakhir di atas -60 dBFS, lalu tambah 1 detik hening.

    Ekor reverb tidak pernah terpotong selama masih di atas -60 dBFS.
    """
    level = np.abs(audio).max(axis=1) if audio.ndim == 2 else np.abs(audio)
    above = np.flatnonzero(level > 10 ** (floor_db / 20))
    end = int(above[-1]) + 1 if len(above) else 0
    silence = np.zeros((int(silence_s * samplerate),) + audio.shape[1:], dtype=audio.dtype)
    return np.concatenate([audio[:end], silence])


def to_pcm24_tpdf(audio: np.ndarray, seed: int | None = None) -> np.ndarray:
    """Kuantisasi ke 24-bit dengan dither TPDF (+-1 LSB), dikemas sebagai int32 (24 bit atas)."""
    rng = np.random.default_rng(seed)
    scale = float(2**23)
    dither = rng.random(audio.shape, dtype=np.float32) - rng.random(audio.shape, dtype=np.float32)
    q = np.rint(audio.astype(np.float64) * scale + dither)
    np.clip(q, -scale, scale - 1, out=q)
    return q.astype(np.int32) << 8


def write_wav(path: Path, audio: np.ndarray, samplerate: int = SAMPLE_RATE, seed: int | None = None) -> None:
    if path.exists():
        raise FileExistsError(f"File sudah ada, tidak akan ditimpa: {path}")
    sf.write(str(path), to_pcm24_tpdf(audio, seed), samplerate, subtype="PCM_24", format="WAV")


def decode_audio(path: Path) -> np.ndarray:
    """Dekode file apa pun lewat FFmpeg menjadi float32 stereo 48 kHz."""
    cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-i", str(path),
           "-f", "f32le", "-ac", "2", "-ar", str(SAMPLE_RATE), "-"]
    proc = subprocess.run(cmd, capture_output=True, creationflags=_no_window())
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg gagal mendekode {path.name}: {proc.stderr.decode(errors='replace')[-300:]}")
    return np.frombuffer(proc.stdout, dtype=np.float32).reshape(-1, 2)


@dataclass(frozen=True)
class Mp3Info:
    true_peak_dbtp: float
    trim_db: float


def encode_mp3(wav: Path, mp3: Path, title: str, ceiling_dbtp: float = CEILING_DBTP) -> Mp3Info:
    """MP3 320 kbps CBR dengan tag judul. Jika encoder membuat puncak > ceiling, encode ulang sedikit lebih pelan."""
    if mp3.exists():
        raise FileExistsError(f"File sudah ada, tidak akan ditimpa: {mp3}")
    trim = 0.0
    for attempt in range(4):
        cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y" if attempt else "-n",
               "-i", str(wav)]
        if trim < 0:
            cmd += ["-af", f"volume={trim:.2f}dB"]
        cmd += ["-c:a", "libmp3lame", "-b:a", MP3_BITRATE, "-ar", str(SAMPLE_RATE),
                "-metadata", f"title={title}", "-id3v2_version", "3", str(mp3)]
        proc = subprocess.run(cmd, capture_output=True, creationflags=_no_window())
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg gagal membuat MP3: {proc.stderr.decode(errors='replace')[-300:]}")
        tp = true_peak_db(decode_audio(mp3))
        if tp <= ceiling_dbtp:
            return Mp3Info(tp, trim)
        trim -= (tp - ceiling_dbtp) + 0.1
    return Mp3Info(tp, trim)


def fmt_duration(seconds: float) -> str:
    m, s = divmod(int(round(seconds)), 60)
    return f"{m:02d}:{s:02d}"


def fmt_db(value: float, unit: str) -> str:
    if not math.isfinite(value):
        return f"-inf {unit}"
    return f"{value:.1f} {unit}"
