"""Buat proyek contoh "Contoh SATB" berisi 5 track SINTETIS (bukan rekaman suara asli).

Dipakai untuk mencoba rantai pascaproduksi sebelum ada rekaman nyata. Suara
dibuat dari nada harmonik dengan vibrato; level antar-suara sengaja dibuat
tidak seimbang, dan diberi desis (-55 dBFS) serta dengung rendah 30 Hz agar
efek penyeimbang, kompresor, dan high-pass terdengar.

Cara pakai:
    .venv\\Scripts\\python tools\\make_demo_project.py [--folder projects]
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools._common import ROOT, setup_console  # noqa: E402
from chorale.project import Take, add_recent, create_project  # noqa: E402

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

SR = 48000
TEMPO = 72
BAR = 4 * 60 / TEMPO
# Akor per birama (MIDI): bass, tenor, alto, sopran.
CHORDS = [
    (48, 55, 64, 72), (41, 57, 65, 69), (43, 55, 62, 71), (48, 55, 64, 67),
    (45, 57, 64, 72), (41, 57, 65, 69), (43, 55, 62, 67), (48, 55, 64, 72),
]
VOICE_PEAK_DB = {"bass": -20.0, "tenor": -12.0, "alto": -16.0, "sopran": -8.0}
VOICE_INDEX = {"bass": 0, "tenor": 1, "alto": 2, "sopran": 3}


def hz(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def voice_line(notes: list[int], rng: np.random.Generator) -> np.ndarray:
    n_bar = int(BAR * SR)
    out = np.zeros(n_bar * len(notes))
    t = np.arange(n_bar) / SR
    attack, release = 0.08, 0.15
    env = np.minimum(t / attack, 1.0) * np.clip((BAR - t) / release, 0.0, 1.0)
    for i, midi in enumerate(notes):
        depth = 0.006 * np.clip((t - 0.3) / 0.4, 0, 1)
        f = hz(midi) * (1 + depth * np.sin(2 * np.pi * 5.5 * t + rng.uniform(0, 6)))
        phase = 2 * np.pi * np.cumsum(f) / SR
        tone = np.zeros_like(t)
        for h in range(1, 16):
            fh = hz(midi) * h
            if fh > 9000:
                break
            formant = 1.0 + 1.5 * np.exp(-((fh - 700) / 300) ** 2) + 0.8 * np.exp(-((fh - 2600) / 500) ** 2)
            tone += formant * np.sin(h * phase) / h ** 1.3
        out[i * n_bar:(i + 1) * n_bar] = tone * env
    return out


def piano_part(rng: np.random.Generator, chords: list[tuple]) -> np.ndarray:
    n_bar = int(BAR * SR)
    beat = n_bar // 4
    out = np.zeros((n_bar * len(chords), 2))
    t = np.arange(n_bar) / SR
    env = np.exp(-t * 1.5) * np.minimum(t / 0.004, 1.0)
    for i, chord in enumerate(chords):
        for b in (0, 2):
            start = i * n_bar + b * beat
            for k, midi in enumerate((chord[0] - 12,) + chord[1:]):
                tone = sum(np.sin(2 * np.pi * hz(midi) * h * t) * np.exp(-t * h * 0.6) / h ** 1.5
                           for h in (1, 2, 3, 4, 5))
                pan = 0.3 + 0.13 * k
                seg = (tone * env)[: len(out) - start]
                out[start:start + len(seg), 0] += seg * (1 - pan)
                out[start:start + len(seg), 1] += seg * pan
    return out


def finish(audio: np.ndarray, peak_db: float, rng: np.random.Generator) -> np.ndarray:
    audio = audio * (10 ** (peak_db / 20) / np.max(np.abs(audio)))
    t = np.arange(len(audio)) / SR
    rumble = 10 ** (-40 / 20) * np.sin(2 * np.pi * 30 * t)
    hiss = 10 ** (-55 / 20) * rng.standard_normal(audio.shape)
    if audio.ndim == 2:
        rumble = rumble[:, None]
    return (audio + rumble + hiss).astype(np.float32)


def create_demo(folder: Path, title: str = "Contoh SATB", bars: int = len(CHORDS)):
    """Buat proyek sintetis berisi `bars` birama (8 birama = 26,7 detik pada 72 BPM)."""
    rng = np.random.default_rng(2026)
    chords = [CHORDS[i % len(CHORDS)] for i in range(bars)]
    folder.mkdir(parents=True, exist_ok=True)
    project = create_project(folder, title, tempo=TEMPO, time_signature="4/4", count_in_bars=1)
    when = datetime.now()
    parts = {"piano": finish(piano_part(rng, chords), -10.0, rng)}
    for name in ("bass", "tenor", "alto", "sopran"):
        notes = [c[VOICE_INDEX[name]] for c in chords]
        parts[name] = finish(voice_line(notes, rng), VOICE_PEAK_DB[name], rng)
    for track_id, audio in parts.items():
        number, path = project.next_take_path(track_id, when)
        sf.write(str(path), audio, SR, subtype="PCM_24")
        project.add_take(track_id, Take(number, path.name, when.isoformat(timespec="seconds"),
                                        round(len(audio) / SR, 3)))
    return project


def main() -> int:
    setup_console()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--folder", type=Path, default=ROOT / "projects")
    parser.add_argument("--birama", type=int, default=len(CHORDS), help="jumlah birama (72 = 4 menit)")
    args = parser.parse_args()

    project = create_demo(args.folder, bars=args.birama)
    add_recent(project)
    print(f"Proyek contoh (sintetis) dibuat: {project.folder}")
    print(f"Durasi {project.tracks['piano'].active_take.duration:.1f} detik, 5 track.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
