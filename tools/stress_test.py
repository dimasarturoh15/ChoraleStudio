"""Stress test engine rekam + putar selama N menit, hitung dropout.

Memakai engine aplikasi yang sebenarnya (AudioSession): input direkam ke WAV
24-bit lewat ring buffer + thread penulis disk, sementara output memutar
campuran track. Musik panduan diputar sangat pelan (-60 dB) dan metronom mati,
agar aman untuk telinga.

Proyek uji dibuat di folder sementara Windows dan file rekamannya dihapus di
akhir (kecuali --simpan).

--loopback (butuh kabel Output -> Input 1, phantom dan direct monitor mati):
metronom 60 BPM berbunyi sepanjang uji dan rekamannya dianalisis tiap 10 detik.
Ini menangkap lompatan latensi yang TIDAK dilaporkan PortAudio sebagai dropout
(ditemukan pada SC202HD, 07-11-2026): driver menyisipkan jeda pada playback
sehingga penyanyi mendengar klik dan take bergeser beberapa milidetik.

Cara pakai:
    .venv\\Scripts\\python tools\\stress_test.py [--minutes 10] [--blocksize 256] [--device SC202]
Tekan Ctrl+C untuk berhenti lebih awal (ringkasan tetap ditampilkan).
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools._common import heading, setup_console  # noqa: E402
from chorale.audio import device as devices  # noqa: E402
from chorale.audio.device import AudioDeviceError, select_device  # noqa: E402
from chorale.audio.calibration import estimate_delay  # noqa: E402
from chorale.audio.metronome import Metronome  # noqa: E402
from chorale.audio.session import WARMUP_SECONDS, AudioSession  # noqa: E402
from chorale.project import Take, create_project  # noqa: E402

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

SR = devices.SAMPLE_RATE
LOOPBACK_TEMPO = 60          # satu klik per detik
CHECK_EVERY_S = 10.0         # jarak titik ukur latensi di rekaman
# Jendela ukur memuat tepat satu klik dan jeda dicari sampai MAX_LAG_S saja; klik datang
# tiap 1 detik, jadi jendela yang lebih panjang bisa tertukar dengan klik berikutnya.
CHECK_WINDOW_S = 0.5
MAX_LAG_S = 0.3
JUMP_TOLERANCE = 24          # sampel (0,5 ms); lebih dari ini dihitung lompatan
MIN_QUALITY = 1000


def analyze_loopback(path: Path, metronome: Metronome, every_s: float = CHECK_EVERY_S,
                     window_s: float = CHECK_WINDOW_S) -> list[tuple[float, int]]:
    """Jeda klik metronom di rekaman loopback, diukur tiap `every_s` detik: [(detik, jeda_sampel)].

    Rekaman dimulai pada frame lagu 0 (latency_samples=0), jadi klik pada frame lagu p
    muncul di p + L. `every_s` harus kelipatan 1 detik agar tiap jendela diawali klik.
    Titik yang kliknya tidak tertangkap jelas dilewati.
    """
    info = sf.info(str(path))
    window = int(window_s * SR)
    margin = int(MAX_LAG_S * SR)
    points = []
    start = 0
    with sf.SoundFile(str(path)) as f:
        while start + window + margin <= info.frames:
            f.seek(start)
            rec = f.read(window + margin, dtype="float32", always_2d=True)[:, 0]
            ref = metronome.click_train(window, song_start=start)
            est = estimate_delay(rec, ref)
            if est.quality >= MIN_QUALITY:
                points.append((start / SR, int(est.lag_samples)))
            start += int(every_s * SR)
    return points


def find_jumps(points: list[tuple[float, int]], tolerance: int = JUMP_TOLERANCE) -> list[tuple[float, int, int]]:
    """Perubahan jeda antar-titik yang lebih dari `tolerance`: [(detik, jeda_lama, jeda_baru)]."""
    return [(t, prev, lag) for (_, prev), (t, lag) in zip(points, points[1:]) if abs(lag - prev) > tolerance]


def make_guide(project, minutes: float) -> None:
    """Pasang take piano berisi derau pelan (maks. 5 menit, agar hemat RAM) untuk diputar."""
    when = datetime.now()
    number, path = project.next_take_path("piano", when)
    frames = int((min(minutes, 5.0) * 60 + 5) * SR)
    rng = np.random.default_rng(0)
    with sf.SoundFile(str(path), "w", SR, 2, "PCM_24", format="WAV") as f:
        chunk = SR * 10
        for start in range(0, frames, chunk):
            n = min(chunk, frames - start)
            f.write((0.25 * rng.uniform(-1, 1, (n, 2))).astype(np.float32))
    project.add_take("piano", Take(number, path.name, when.isoformat(timespec="seconds"), frames / SR))


def main() -> int:
    setup_console()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--device", default="SC202", help="kata kunci nama sound card")
    parser.add_argument("--blocksize", type=int, default=devices.DEFAULT_BLOCKSIZE,
                        choices=devices.BLOCKSIZE_CHOICES)
    parser.add_argument("--minutes", type=float, default=10.0, help="durasi uji (default 10)")
    parser.add_argument("--interval", type=float, default=60.0, help="jeda laporan progres (detik)")
    parser.add_argument("--simpan", action="store_true", help="jangan hapus proyek uji di akhir")
    parser.add_argument("--loopback", action="store_true",
                        help="deteksi lompatan latensi lewat kabel loopback (metronom 60 BPM)")
    args = parser.parse_args()

    try:
        selection = select_device(args.device)
    except AudioDeviceError as exc:
        print(f"  {exc}")
        return 1

    workdir = Path(tempfile.mkdtemp(prefix="harmonisatb_stress_"))
    project = create_project(workdir, "Stress Test", count_in_bars=0, metronome_after_count_in=False,
                             tempo=LOOPBACK_TEMPO)
    print("  Menyiapkan musik panduan uji...")
    make_guide(project, args.minutes)
    session = AudioSession(project, selection, record_track="bass", blocksize=args.blocksize,
                           monitor_gain_db=-60.0, metronome=args.loopback, metronome_volume_db=-12.0,
                           latency_samples=0, warmup_seconds=WARMUP_SECONDS)

    heading("Stress test engine rekam + putar")
    print(f"  Mode    : {selection.mode_label}, {SR} Hz, buffer {args.blocksize} "
          f"({args.blocksize / SR * 1000:.2f} ms)")
    print(f"  Input   : {selection.input.name} (rekam 1 kanal ke WAV 24-bit)")
    print(f"  Output  : {selection.output.name} (musik panduan -60 dB"
          + (", klik metronom 60 BPM untuk loopback)" if args.loopback else ")"))
    print(f"  Durasi  : {args.minutes:g} menit. Ctrl+C untuk berhenti lebih awal.")
    print(f"  Mulai   : {datetime.now():%H:%M:%S}")
    print()

    cpu_loads: list[float] = []
    stopped_early = device_lost = False
    duration = args.minutes * 60
    try:
        session.start()
    except AudioDeviceError as exc:
        print(f"  GAGAL membuka sound card: {exc}\n  (teknis: {exc.technical})")
        return 1
    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    next_report = args.interval
    try:
        while session.warming_up:
            time.sleep(0.1)
        wall_start = time.perf_counter()
        while (elapsed := time.perf_counter() - wall_start) < duration:
            time.sleep(1.0)
            cpu_loads.append(session.cpu_load)
            if session.device_lost:
                device_lost = True
                print("  Sound card terputus!")
                break
            if elapsed >= next_report:
                next_report += args.interval
                st = session.status()
                print(f"  [{elapsed / 60:5.1f} menit] dropout: {st.dropouts}, "
                      f"beban callback: {session.cpu_load * 100:.1f}%, "
                      f"terekam: {st.recorded_seconds / 60:.1f} menit", flush=True)
    except KeyboardInterrupt:
        stopped_early = True
    wall = time.perf_counter() - wall_start
    cpu = time.process_time() - cpu_start
    overruns = session.recorder.overrun_frames
    flag_counts = session._flag_counts.copy()
    take = session.stop()

    heading("RINGKASAN")
    print(f"  Selesai                : {datetime.now():%H:%M:%S}")
    print(f"  Durasi berjalan        : {wall / 60:.2f} menit" + (" (dihentikan lebih awal)" if stopped_early else ""))
    print(f"  TOTAL DROPOUT          : {int(flag_counts.sum())}")
    for i, name in enumerate(("input meluap", "input kurang", "output kosong (klik)", "output meluap")):
        if flag_counts[i]:
            print(f"    - {name}: {int(flag_counts[i])}")
    print(f"  Data hilang di ring    : {overruns} sampel (penulis disk tertinggal)")
    if take is not None:
        path = project.take_path(take)
        info = sf.info(str(path))
        print(f"  File rekaman           : {info.duration / 60:.2f} menit, {info.subtype}, "
              f"{path.stat().st_size / 1024**2:.0f} MB (selisih dari waktu jam: "
              f"{(info.frames - wall * SR) / SR * 1000:+.0f} ms)")
    if cpu_loads:
        print(f"  Beban callback audio   : rata-rata {np.mean(cpu_loads) * 100:.1f}%, "
              f"maks {np.max(cpu_loads) * 100:.1f}%")
    print(f"  CPU proses Python      : {cpu / wall * 100:.1f}% dari 1 inti "
          f"({cpu / wall * 100 / (os.cpu_count() or 1):.1f}% dari total {os.cpu_count()} inti)")
    for w in session.warnings:
        if "lebih pendek dari 90%" not in w:
            print(f"  Peringatan             : {w}")

    jumps: list = []
    if args.loopback and take is not None:
        points = analyze_loopback(project.take_path(take), session.metronome)
        jumps = find_jumps(points)
        lags = [lag for _, lag in points]
        heading("LOMPATAN LATENSI (loopback)")
        if not points:
            print("  Klik tidak tertangkap. Cek kabel loopback dan naikkan gain Input 1.")
        else:
            print(f"  Titik ukur             : {len(points)} (tiap {CHECK_EVERY_S:g} detik)")
            print(f"  Jeda awal / akhir      : {lags[0]} / {lags[-1]} sampel "
                  f"({lags[0] / SR * 1000:.2f} / {lags[-1] / SR * 1000:.2f} ms)")
            print(f"  Rentang jeda           : {min(lags)} - {max(lags)} sampel "
                  f"({(max(lags) - min(lags)) / SR * 1000:.2f} ms)")
            print(f"  LOMPATAN (> {JUMP_TOLERANCE} sampel) : {len(jumps)}")
            for t, old, new in jumps[:20]:
                print(f"    - menit {t / 60:6.2f}: {old} -> {new} sampel ({(new - old) / SR * 1000:+.2f} ms)")

    if args.simpan:
        print(f"  Proyek uji disimpan di : {project.folder}")
    else:
        shutil.rmtree(workdir, ignore_errors=True)
    ok = flag_counts.sum() == 0 and overruns == 0 and not stopped_early and not device_lost and not jumps
    print()
    print(("  -> LULUS: tidak ada dropout" + (" dan tidak ada lompatan latensi." if args.loopback else "."))
          if ok else "  -> TIDAK LULUS (lihat rincian di atas).")
    print()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
