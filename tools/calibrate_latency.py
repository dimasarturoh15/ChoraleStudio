r"""Ukur latensi round-trip (putar -> rekam) sound card dengan kabel loopback.

Memakai chorale.audio.calibration.measure_latency (logika yang sama dengan
tombol "Mulai Kalibrasi" di layar Pengaturan). Hasil disimpan ke
%APPDATA%\HarmoniSATB\calibration.json.

Cara pakai:
    .venv\Scripts\python tools\calibrate_latency.py [--runs 5] [--blocksize 256] [--shared] [--yes]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools._common import heading, setup_console  # noqa: E402
from chorale.audio.calibration import (  # noqa: E402
    SAFETY_STEPS, CalibrationError, accuracy_label, measure_latency, save_calibration,
)
from chorale.audio.device import (  # noqa: E402
    BLOCKSIZE_CHOICES, DEFAULT_BLOCKSIZE, MODE_ASIO, MODE_EXCLUSIVE, MODE_SHARED, AudioDeviceError,
    select_device,
)

SR = 48000


def main() -> int:
    setup_console()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--device", default="SC202", help="kata kunci nama sound card")
    parser.add_argument("--hostapi", choices=("wasapi", "asio"), default="wasapi")
    parser.add_argument("--shared", action="store_true", help="pakai WASAPI Shared")
    parser.add_argument("--blocksize", type=int, default=DEFAULT_BLOCKSIZE, choices=BLOCKSIZE_CHOICES)
    parser.add_argument("--runs", type=int, default=5, help="jumlah percobaan (default 5)")
    parser.add_argument("--yes", action="store_true", help="lewati konfirmasi Enter")
    parser.add_argument("--no-save", action="store_true", help="jangan simpan hasil")
    args = parser.parse_args()

    mode = MODE_ASIO if args.hostapi == "asio" else (MODE_SHARED if args.shared else MODE_EXCLUSIVE)
    try:
        selection = select_device(args.device, mode=mode)
    except AudioDeviceError as exc:
        print(f"  {exc}")
        return 1

    heading("Kalibrasi latensi round-trip")
    print(f"  Mode   : {selection.mode_label}, {SR} Hz, buffer {args.blocksize}")
    print(f"  Input  : [{selection.input.index}] {selection.input.name}")
    print(f"  Output : [{selection.output.index}] {selection.output.name}")
    print("\nSEBELUM MULAI (penting, demi keamanan telinga dan peralatan):")
    for i, step in enumerate(SAFETY_STEPS, 1):
        print(f"  {i}. {step}")
    print('Sinyal uji berupa bunyi "siul naik" pendek sekitar 0,5 detik pada -6 dBFS.')
    if not args.yes:
        input("\nTekan Enter jika kabel loopback sudah terpasang... ")

    def progress(run, runs, lag):
        print(f"  Percobaan {run}/{runs}: jeda {lag} sampel ({lag / SR * 1000:.2f} ms)")

    try:
        result = measure_latency(selection, args.blocksize, args.runs, progress=progress)
    except (CalibrationError, AudioDeviceError) as exc:
        print(f"  GAGAL: {exc}")
        return 1

    label, _ = accuracy_label(result)
    heading("HASIL")
    print(f"  Latensi round-trip : {result.latency_samples} sampel = {result.latency_ms:.2f} ms")
    print(f"  Semua percobaan    : {result.runs_samples} sampel")
    print(f"  Selisih terbesar   : {result.spread_samples} sampel ({result.spread_samples / SR * 1000:.3f} ms)")
    print(f"  Perkiraan PortAudio: {result.reported_latency_ms:.2f} ms (hanya pembanding)")
    print(f"  Penilaian          : {label}")
    if not args.no_save:
        print(f"  Disimpan ke        : {save_calibration(result)}")
    print()
    return 0 if result.spread_samples <= 48 else 1


if __name__ == "__main__":
    sys.exit(main())
