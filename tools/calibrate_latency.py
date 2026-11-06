"""Ukur latensi round-trip (putar -> rekam) sound card dengan kabel loopback.

Sinyal uji (sweep pendek) diputar sambil merekam, lalu jedanya dicari dengan
cross-correlation. Diulang beberapa kali (stream dibuka ulang tiap percobaan,
sama seperti saat aplikasi mulai merekam), lalu hasil disimpan ke
%APPDATA%\\HarmoniSATB\\calibration.json.

Cara pakai:
    .venv\\Scripts\\python tools\\calibrate_latency.py [--runs 5] [--shared] [--yes]
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools._common import (  # noqa: E402
    add_device_args, explain_error, extra_settings_for, heading, mode_label, resolve_pair, setup_console,
)
from chorale.audio import device as devices  # noqa: E402
from chorale.audio.calibration import CalibrationResult, estimate_delay, make_sweep, save_calibration  # noqa: E402

import numpy as np  # noqa: E402
import sounddevice as sd  # noqa: E402

SR = devices.SAMPLE_RATE
MIN_QUALITY = 20.0

INSTRUCTIONS = """\
SEBELUM MULAI (penting, demi keamanan telinga dan peralatan):
  1. Kecilkan volume headphone ke nol / lepas headphone dari kepala.
  2. MATIKAN phantom +48V di sound card.
  3. Sambungkan kabel dari OUTPUT sound card (Line Out L/R atau Headphone)
     ke INPUT 1 sound card (pakai kabel jack, kecilkan gain input dulu).
  4. Kecilkan kenop direct monitor agar suara input tidak ikut terdengar.
Sinyal uji berupa bunyi "siul naik" pendek sekitar 0,5 detik pada -6 dBFS."""


def run_once(dev_in, dev_out, in_ch: int, out_ch: int, args, stimulus: np.ndarray) -> tuple[np.ndarray, float]:
    """Putar stimulus dan rekam bersamaan lewat callback; kembalikan rekaman dan latensi laporan PortAudio."""
    total = len(stimulus)
    play = np.zeros((total, out_ch), dtype=np.float32)
    play[:, :] = stimulus[:, None]
    rec = np.zeros((total, in_ch), dtype=np.float32)
    pos = [0]
    flags = [0]

    def callback(indata, outdata, frames, t, status):
        if status:
            flags[0] += 1
        start = pos[0]
        n = min(frames, total - start)
        if n > 0:
            outdata[:n] = play[start:start + n]
            rec[start:start + n] = indata[:n]
        if n < frames:
            outdata[n:] = 0
        pos[0] = start + frames
        if pos[0] >= total:
            raise sd.CallbackStop

    device = (dev_in.index, dev_out.index)
    with sd.Stream(device=device, channels=(in_ch, out_ch), samplerate=SR, dtype="float32", latency="low",
                   blocksize=args.blocksize, extra_settings=extra_settings_for(args),
                   callback=callback) as stream:
        reported = sum(stream.latency)
        while stream.active:
            time.sleep(0.05)
    if flags[0]:
        print(f"    (peringatan: {flags[0]} blok dengan status dropout)")
    return rec, reported


def main() -> int:
    setup_console()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    add_device_args(parser)
    parser.add_argument("--runs", type=int, default=5, help="jumlah percobaan (default 5)")
    parser.add_argument("--yes", action="store_true", help="lewati konfirmasi Enter")
    parser.add_argument("--no-save", action="store_true", help="jangan simpan hasil")
    args = parser.parse_args()

    dev_in, dev_out = resolve_pair(args.hostapi, args.device)
    in_ch = min(2, dev_in.max_input_channels)
    out_ch = min(2, dev_out.max_output_channels)

    heading("Kalibrasi latensi round-trip")
    print(f"  Mode   : {mode_label(args)}, {SR} Hz, buffer {args.blocksize}")
    print(f"  Input  : [{dev_in.index}] {dev_in.name}")
    print(f"  Output : [{dev_out.index}] {dev_out.name}")
    print()
    print(INSTRUCTIONS)
    if not args.yes:
        input("\nTekan Enter jika kabel loopback sudah terpasang... ")

    sweep = make_sweep(SR)
    lead, tail = int(0.25 * SR), int(1.0 * SR)
    stimulus = np.concatenate([np.zeros(lead, np.float32), sweep, np.zeros(tail, np.float32)])

    lags: list[int] = []
    reported_ms: list[float] = []
    for run in range(1, args.runs + 1):
        try:
            rec, reported = run_once(dev_in, dev_out, in_ch, out_ch, args, stimulus)
        except Exception as exc:  # noqa: BLE001
            print(f"  Percobaan {run}: GAGAL membuka perangkat.\n    Pesan teknis: {exc}\n"
                  f"    Artinya: {explain_error(exc)}")
            return 1
        estimates = [estimate_delay(rec[:, c], stimulus) for c in range(in_ch)]
        best_ch = int(np.argmax([e.quality for e in estimates]))
        est = estimates[best_ch]
        peak_db = 20 * np.log10(max(float(np.max(np.abs(rec[:, best_ch]))), 1e-9))
        lag = est.lag_samples
        print(f"  Percobaan {run}: jeda {lag} sampel ({lag / SR * 1000:.2f} ms), "
              f"input {best_ch + 1}, puncak {peak_db:.1f} dBFS, keyakinan {est.quality:.0f}"
              + (", polaritas terbalik" if est.inverted else ""))
        if est.quality < MIN_QUALITY:
            print("    Sinyal uji tidak tertangkap jelas. Cek kabel loopback, gain input, "
                  "dan pastikan output yang tersambung adalah output sound card ini.")
            return 1
        if peak_db > -1.0:
            print("    Peringatan: input hampir clip. Kecilkan gain input sedikit.")
        lags.append(lag)
        reported_ms.append(reported * 1000)
        time.sleep(0.3)

    median = int(np.median(lags))
    spread = max(lags) - min(lags)
    heading("HASIL")
    print(f"  Latensi round-trip : {median} sampel = {median / SR * 1000:.2f} ms")
    print(f"  Semua percobaan    : {lags} sampel")
    print(f"  Selisih terbesar   : {spread} sampel ({spread / SR * 1000:.3f} ms)")
    print(f"  Perkiraan PortAudio: {np.mean(reported_ms):.2f} ms (hanya pembanding)")
    consistent = spread <= 1
    if consistent:
        print("  -> KONSISTEN (selisih <= 1 sampel). Siap dipakai untuk kompensasi.")
    elif spread / SR * 1000 <= 1.0:
        print("  -> Cukup konsisten (selisih <= 1 ms, masih memenuhi target PRD), tapi belum ideal.")
    else:
        print("  -> TIDAK KONSISTEN (selisih > 1 ms). Latensi berubah tiap stream dibuka.")

    if not args.no_save:
        result = CalibrationResult(
            input_device=dev_in.name, output_device=dev_out.name, hostapi=dev_in.hostapi,
            exclusive=args.hostapi == "wasapi" and not args.shared, samplerate=SR,
            blocksize=args.blocksize, latency_samples=median,
            latency_ms=round(median / SR * 1000, 3), runs_samples=lags, spread_samples=spread,
            reported_latency_ms=round(float(np.mean(reported_ms)), 3),
            date=datetime.now().isoformat(timespec="seconds"),
        )
        path = save_calibration(result)
        print(f"  Disimpan ke        : {path}")
    print()
    return 0 if spread / SR * 1000 <= 1.0 else 1


if __name__ == "__main__":
    sys.exit(main())
