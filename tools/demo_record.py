"""Demo: rekam 10 detik dari mic sambil memutar file uji piano, simpan ke proyek contoh.

Proyek contoh dibuat di folder projects/ (tidak ikut di-commit). Jika track
Piano masih kosong, file uji piano sintetis dibuat dan dipasang sebagai take
Piano, lalu diputar ke headphone selama merekam track Bass.

Cara pakai:
    .venv\\Scripts\\python tools\\demo_record.py [--seconds 10] [--track bass] [--device SC202]
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools._common import ROOT, heading, setup_console  # noqa: E402
from chorale.audio.device import AudioDeviceError, select_device  # noqa: E402
from chorale.audio.meter import meter_zone  # noqa: E402
from chorale.audio.session import AudioSession  # noqa: E402
from chorale.project import TRACK_LABELS, VOCAL_TRACK_IDS, Take, add_recent, create_project, open_project  # noqa: E402

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

SR = 48000
DEMO_TITLE = "Demo Segmen 2"


def synth_piano(seconds: float = 14.0, bpm: int = 72) -> np.ndarray:
    """Progresi akor I-IV-V-I sederhana dengan nada meluruh, stereo, puncak -12 dBFS."""
    chords = [(60, 64, 67), (65, 69, 72), (67, 71, 74), (60, 64, 67)]
    beat = 60 / bpm
    out = np.zeros((int(seconds * SR), 2), dtype=np.float64)
    t_note = np.arange(int(4 * beat * SR)) / SR
    env = np.exp(-t_note * 1.8) * np.minimum(t_note / 0.005, 1.0)
    for bar in range(int(seconds / (4 * beat))):
        start = int(bar * 4 * beat * SR)
        for k, midi in enumerate(chords[bar % 4]):
            f = 440 * 2 ** ((midi - 69) / 12)
            tone = sum(np.sin(2 * np.pi * f * h * t_note) / h**1.5 for h in (1, 2, 3, 4))
            pan = 0.35 + 0.15 * k
            end = min(start + len(tone), len(out))
            out[start:end, 0] += (tone * env)[: end - start] * (1 - pan)
            out[start:end, 1] += (tone * env)[: end - start] * pan
    out *= 10 ** (-12 / 20) / np.max(np.abs(out))
    return out.astype(np.float32)


def ensure_project(folder: Path):
    existing = folder / DEMO_TITLE
    if (existing / "proyek.json").is_file():
        return open_project(existing)
    folder.mkdir(parents=True, exist_ok=True)
    return create_project(folder, DEMO_TITLE, tempo=72, time_signature="4/4", count_in_bars=0)


def ensure_piano(project) -> None:
    if project.tracks["piano"].has_audio:
        return
    when = datetime.now()
    number, path = project.next_take_path("piano", when)
    audio = synth_piano()
    sf.write(str(path), audio, SR, subtype="PCM_24")
    project.add_take("piano", Take(number, path.name, when.isoformat(timespec="seconds"),
                                   round(len(audio) / SR, 3)))
    print(f"  File uji piano dibuat: {path.name}")


def bar(db: float, width: int = 30) -> str:
    filled = int(max(0.0, min(1.0, (db + 60) / 60)) * width)
    return "#" * filled + "-" * (width - filled)


def main() -> int:
    setup_console()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seconds", type=float, default=10.0)
    parser.add_argument("--track", choices=VOCAL_TRACK_IDS, default="bass")
    parser.add_argument("--device", default="SC202", help="kata kunci nama sound card")
    parser.add_argument("--input", type=int, default=1, help="nomor input mic (1 atau 2)")
    parser.add_argument("--folder", type=Path, default=ROOT / "projects")
    parser.add_argument("--monitor-gain-db", type=float, default=0.0,
                        help="volume musik panduan di headphone (dB)")
    parser.add_argument("--blocksize", type=int, default=256, choices=(128, 256, 512, 1024))
    parser.add_argument("--yes", action="store_true", help="lewati konfirmasi Enter")
    args = parser.parse_args()

    heading("Demo rekam HarmoniSATB Studio")
    try:
        selection = select_device(args.device)
    except AudioDeviceError as exc:
        print(f"  {exc}")
        return 1
    print(f"  Sound card : {selection.input.name} / {selection.output.name}")
    print(f"  Mode       : {selection.mode_label}, 48 kHz, buffer {args.blocksize}")

    project = ensure_project(args.folder)
    ensure_piano(project)
    print(f"  Proyek     : {project.folder}")

    try:
        session = AudioSession(project, selection, record_track=args.track, blocksize=args.blocksize,
                               input_first_channel=args.input - 1, monitor_gain_db=args.monitor_gain_db)
    except ValueError as exc:
        print(f"  {exc}")
        return 1
    for w in session.warnings:
        print(f"  PERINGATAN: {w}")

    label = TRACK_LABELS[args.track]
    print()
    print(f"  Akan merekam track {label} selama {args.seconds:g} detik dari INPUT {args.input}.")
    print("  Pakai headphone: Anda akan mendengar piano uji. Suara Anda sendiri TIDAK diputar")
    print("  oleh aplikasi; dengarkan lewat kenop direct monitor sound card.")
    if not args.yes:
        input("\n  Tekan Enter jika sudah siap... ")
    for n in (3, 2, 1):
        print(f"  {n}...")
        time.sleep(1)

    try:
        session.start()
    except AudioDeviceError as exc:
        print(f"  Gagal membuka sound card: {exc}\n  (teknis: {exc.technical})")
        return 1
    print("\n  >>> BERSUARALAH SEKARANG (bernyanyi atau bicara ke mic) <<<\n")

    peak_max = -120.0
    try:
        while (remaining := args.seconds - session.player.position_seconds) > 0:
            time.sleep(min(0.5, remaining))
            st = session.status()
            db = float(st.peaks_db[args.input - 1])
            peak_max = max(peak_max, db)
            clip = "  CLIP!" if st.clip[args.input - 1] else ""
            zone = meter_zone(db).replace("kosong", "terlalu pelan")
            print(f"  {st.elapsed:5.1f} s  input {args.input} [{bar(db)}] {db:6.1f} dBFS ({zone}){clip}")
            if st.device_lost:
                print("  Sound card terputus!")
                break
    except KeyboardInterrupt:
        print("  Dihentikan.")
    take = session.stop()

    heading("HASIL")
    for w in session.warnings:
        print(f"  PERINGATAN: {w}")
    if take is None:
        print("  Tidak ada audio yang terekam.")
        return 1
    path = project.take_path(take)
    info = sf.info(str(path))
    audio, _ = sf.read(str(path), dtype="float32")
    peak = 20 * np.log10(max(float(np.max(np.abs(audio))), 1e-6))
    print(f"  Take       : {take.label} ({'lengkap' if take.complete else 'TIDAK lengkap'})")
    print(f"  File       : {path}")
    print(f"  Format     : {info.samplerate} Hz, {info.channels} kanal, {info.subtype}, "
          f"{info.duration:.2f} detik")
    print(f"  Puncak     : {peak:.1f} dBFS (meter selama rekam: maks {peak_max:.1f} dBFS)")
    print(f"  Dropout    : {session.dropouts}")
    if peak < -50:
        print("  Catatan    : rekaman sangat pelan/hening. Cek gain mic, phantom +48V, dan nomor input.")
    elif peak > -1:
        print("  Catatan    : hampir clip. Kecilkan gain mic sedikit.")
    add_recent(project)
    print()
    return 0 if session.dropouts == 0 and take.complete else 1


if __name__ == "__main__":
    sys.exit(main())
