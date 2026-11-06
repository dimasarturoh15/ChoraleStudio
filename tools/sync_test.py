"""Uji sinkron 5 track lewat kabel loopback (gerbang Sprint 1: selisih <= 1 ms).

Langkah:
  1. Piano direkam: metronom berbunyi ke output, masuk lagi lewat kabel loopback.
  2. Bass, Tenor, Alto, Sopran direkam berurutan: tiap track mendengar piano
     (di-solo, metronom mati) lewat kabel loopback, sama seperti penyanyi
     yang mengikuti piano di headphone.
  3. Posisi klik di setiap take dibandingkan dengan grid ketukan.

Butuh hasil kalibrasi dari tools\\calibrate_latency.py dengan buffer yang sama.

Cara pakai:
    .venv\\Scripts\\python tools\\sync_test.py [--detik 8] [--buffer 256] [--yes] [--simpan]
"""

from __future__ import annotations

import argparse
import itertools
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools._common import heading, setup_console  # noqa: E402
from chorale.audio.calibration import estimate_delay, find_calibration  # noqa: E402
from chorale.audio.device import BLOCKSIZE_CHOICES, DEFAULT_BLOCKSIZE, AudioDeviceError, select_device  # noqa: E402
from chorale.audio.metronome import Metronome  # noqa: E402
from chorale.audio.session import AudioSession  # noqa: E402
from chorale.project import TRACK_IDS, TRACK_LABELS, create_project  # noqa: E402

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

SR = 48000
LIMIT_SAMPLES = 48  # 1 ms
TEMPO = 120

INSTRUCTIONS = """\
SEBELUM MULAI (penting):
  1. Kecilkan volume headphone / lepas headphone.
  2. MATIKAN phantom +48V.
  3. Kabel loopback: OUTPUT sound card -> INPUT 1 (sama seperti saat kalibrasi).
  4. Putar kenop DIRECT MONITOR ke posisi playback penuh / input nol.
     Jika direct monitor menyala, input ikut keluar lagi ke output dan bisa
     terjadi dengung (feedback) lewat kabel loopback.
Bunyi yang diputar: klik metronom 120 BPM, sekitar {total:.0f} detik total."""


def record(project, selection, track, seconds, blocksize, metronome) -> tuple:
    session = AudioSession(project, selection, record_track=track, blocksize=blocksize,
                           record_channels=1, metronome=metronome, metronome_volume_db=-12.0)
    session.start()
    while session.song_seconds < seconds:
        time.sleep(0.05)
        if session.device_lost:
            break
    take = session.stop()
    return session, take


def main() -> int:
    setup_console()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--device", default="SC202")
    parser.add_argument("--buffer", type=int, choices=BLOCKSIZE_CHOICES, default=DEFAULT_BLOCKSIZE)
    parser.add_argument("--detik", type=float, default=8.0, help="durasi tiap track (detik)")
    parser.add_argument("--yes", action="store_true", help="lewati konfirmasi Enter")
    parser.add_argument("--simpan", action="store_true", help="simpan proyek uji (default dihapus)")
    args = parser.parse_args()

    try:
        selection = select_device(args.device)
    except AudioDeviceError as exc:
        print(f"  {exc}")
        return 1
    cal = find_calibration(selection.input.name, selection.output.name, selection.hostapi,
                           selection.exclusive, args.buffer)

    heading("Uji sinkron 5 track (loopback)")
    print(f"  Sound card : {selection.mode_label}, buffer {args.buffer}")
    if cal is None:
        print("  Kalibrasi  : BELUM ADA untuk kombinasi ini. Jalankan dulu:")
        print(f"               .venv\\Scripts\\python tools\\calibrate_latency.py --blocksize {args.buffer}")
        return 1
    print(f"  Kalibrasi  : {cal.latency_samples} sampel ({cal.latency_ms:.2f} ms), {cal.date}")
    print()
    print(INSTRUCTIONS.format(total=5 * (args.detik + 2)))
    if not args.yes:
        input("\n  Tekan Enter jika kabel loopback sudah terpasang... ")

    workdir = Path(tempfile.mkdtemp(prefix="harmonisatb_sync_"))
    project = create_project(workdir, "Uji Sinkron", tempo=TEMPO, time_signature="4/4",
                             count_in_bars=1, metronome_after_count_in=True)
    try:
        dropouts = 0
        for track in TRACK_IDS:
            is_piano = track == "piano"
            print(f"  Merekam {TRACK_LABELS[track]:<12}...", end="", flush=True)
            session, take = record(project, selection, track, args.detik, args.buffer,
                                   metronome=True if is_piano else False)
            dropouts += session.dropouts
            if take is None:
                print(" GAGAL (tidak ada audio)")
                return 1
            print(f" {take.duration:.1f} s, dropout {session.dropouts}")
            if is_piano:
                project.set_solo("piano", True)

        reference = Metronome(TEMPO, "4/4").click_train(int((args.detik + 1) * SR))
        offsets: dict[str, float] = {}
        heading("HASIL")
        print(f"  {'Track':<12} {'Posisi klik vs grid':>22}  {'Keyakinan':>9}  Puncak")
        for track in TRACK_IDS:
            audio, _ = sf.read(str(project.take_path(project.tracks[track].active_take)),
                               dtype="float32", always_2d=True)
            est = estimate_delay(audio[:, 0], reference)
            peak = 20 * np.log10(max(float(np.max(np.abs(audio))), 1e-9))
            offsets[track] = est.lag_fractional
            print(f"  {TRACK_LABELS[track]:<12} {est.lag_fractional:+8.2f} sampel ({est.lag_fractional / 48:+6.3f} ms)"
                  f"  {est.quality:9.0f}  {peak:6.1f} dBFS")
            if est.quality < 20:
                print("    -> Klik tidak tertangkap jelas. Cek kabel loopback dan gain input.")
                return 1

        spread = max(abs(a - b) for a, b in itertools.combinations(offsets.values(), 2))
        print()
        print(f"  Selisih terbesar antar-track : {spread:.2f} sampel = {spread / 48:.3f} ms (batas 1 ms)")
        print(f"  Total dropout                : {dropouts}")
        ok = spread <= LIMIT_SAMPLES and dropouts == 0
        print("  -> LULUS: 5 track sejajar." if ok else "  -> TIDAK LULUS.")
        print()
        if args.simpan:
            print(f"  Proyek uji disimpan di: {project.folder}")
        return 0 if ok else 1
    finally:
        if not args.simpan:
            shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
