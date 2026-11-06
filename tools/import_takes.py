r"""Impor file WAV/FLAC sebagai take (alat uji: mengisi 5 track tanpa merekam).

Audio diubah ke 48 kHz, 24-bit; piano stereo, vokal mono. Setiap impor menjadi
take baru (take lama tidak dihapus) dan langsung menjadi take aktif.

Cara pakai:
    .venv\Scripts\python tools\import_takes.py --proyek FOLDER --piano p.wav --bass b.wav ...
    .venv\Scripts\python tools\import_takes.py --proyek FOLDER --contoh   (5 track SATB sintetis)
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from math import gcd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools._common import setup_console  # noqa: E402
from chorale.project import TRACK_IDS, Take, add_recent, open_project  # noqa: E402

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
from scipy import signal  # noqa: E402

SR = 48000


def to_track_format(audio: np.ndarray, samplerate: int, channels: int) -> np.ndarray:
    audio = audio if audio.ndim == 2 else audio[:, None]
    if samplerate != SR:
        g = gcd(SR, samplerate)
        audio = signal.resample_poly(audio, SR // g, samplerate // g, axis=0)
    if channels == 1:
        audio = audio.mean(axis=1, keepdims=True)
    elif audio.shape[1] == 1:
        audio = np.repeat(audio, 2, axis=1)
    else:
        audio = audio[:, :2]
    return np.clip(audio, -1.0, 1.0).astype(np.float32)


def import_take(project, track_id: str, audio: np.ndarray, samplerate: int = SR) -> Take:
    """Simpan audio sebagai take baru di track; nama file mengikuti aturan proyek."""
    track = project.track(track_id)
    data = to_track_format(audio, samplerate, track.channels)
    when = datetime.now()
    number, path = project.next_take_path(track_id, when)
    sf.write(str(path), data, SR, subtype="PCM_24")
    take = Take(number, path.name, when.isoformat(timespec="seconds"), round(len(data) / SR, 3))
    project.add_take(track_id, take)
    return take


def import_file(project, track_id: str, source: Path) -> Take:
    audio, sr = sf.read(str(source), dtype="float32", always_2d=True)
    return import_take(project, track_id, audio, sr)


def import_demo(project, bars: int = 8) -> None:
    """Isi kelima track dengan suara SATB sintetis (lihat make_demo_project)."""
    from tools.make_demo_project import CHORDS, VOICE_INDEX, VOICE_PEAK_DB, finish, piano_part, voice_line

    rng = np.random.default_rng(2026)
    chords = [CHORDS[i % len(CHORDS)] for i in range(bars)]
    import_take(project, "piano", finish(piano_part(rng, chords), -10.0, rng))
    for name in ("bass", "tenor", "alto", "sopran"):
        notes = [c[VOICE_INDEX[name]] for c in chords]
        import_take(project, name, finish(voice_line(notes, rng), VOICE_PEAK_DB[name], rng))


def main() -> int:
    setup_console()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--proyek", type=Path, required=True, help="folder proyek")
    for tid in TRACK_IDS:
        parser.add_argument(f"--{tid}", type=Path, help=f"file audio untuk track {tid}")
    parser.add_argument("--contoh", action="store_true", help="isi 5 track dengan suara sintetis")
    parser.add_argument("--birama", type=int, default=8, help="panjang contoh sintetis (birama)")
    args = parser.parse_args()

    project = open_project(args.proyek)
    if args.contoh:
        import_demo(project, args.birama)
    for tid in TRACK_IDS:
        source = getattr(args, tid)
        if source is not None:
            take = import_file(project, tid, source)
            print(f"  {project.track(tid).label:<12} ← {source.name} ({take.duration:.1f} s)")
    add_recent(project)
    for tid in TRACK_IDS:
        t = project.tracks[tid].active_take
        print(f"  {project.tracks[tid].label:<12} {t.label + f' ({t.duration:.1f} s)' if t else '-'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
