"""Uji membuka sound card di WASAPI Exclusive (lalu Shared jika gagal), 48 kHz, buffer 256.

Yang diuji:
  - input 1 kanal dan 2 kanal (apakah 2 input bisa direkam terpisah)
  - output 2 kanal
  - apakah 48 kHz bisa dikunci dan 24-bit didukung (mode Exclusive)
  - rekam + putar bersamaan 3 detik, hitung dropout

Cara pakai:
    .venv\\Scripts\\python tools\\test_wasapi.py [--device SC202] [--blocksize 256]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools._common import explain_error, heading, resolve_pair, setup_console, wasapi_settings  # noqa: E402
from chorale.audio import device as devices  # noqa: E402

import numpy as np  # noqa: E402
import sounddevice as sd  # noqa: E402

SR = devices.SAMPLE_RATE


def try_input(dev, channels: int, exclusive: bool, blocksize: int) -> dict:
    """Buka input, rekam 1 detik, laporkan level tiap kanal."""
    result = {"ok": False}
    try:
        with sd.InputStream(device=dev.index, channels=channels, samplerate=SR, dtype="float32", latency="low",
                            blocksize=blocksize, extra_settings=wasapi_settings(exclusive)) as s:
            frames = []
            end = time.monotonic() + 1.0
            while time.monotonic() < end:
                data, _ = s.read(blocksize)
                frames.append(data.copy())
            audio = np.concatenate(frames)
            result.update(ok=True, samplerate=s.samplerate, latency_ms=s.latency * 1000,
                          peaks_db=[20 * np.log10(max(np.max(np.abs(audio[:, c])), 1e-9))
                                    for c in range(channels)])
    except Exception as exc:  # noqa: BLE001 - laporkan semua error ke pengguna
        result["error"] = exc
    return result


def try_output(dev, channels: int, exclusive: bool, blocksize: int) -> dict:
    """Buka output dan putar hening 0,5 detik."""
    result = {"ok": False}
    try:
        with sd.OutputStream(device=dev.index, channels=channels, samplerate=SR, dtype="float32", latency="low",
                             blocksize=blocksize, extra_settings=wasapi_settings(exclusive)) as s:
            silence = np.zeros((blocksize, channels), dtype=np.float32)
            for _ in range(int(0.5 * SR / blocksize)):
                s.write(silence)
            result.update(ok=True, samplerate=s.samplerate, latency_ms=s.latency * 1000)
    except Exception as exc:  # noqa: BLE001
        result["error"] = exc
    return result


def check_format(dev, channels: int, dtype: str, is_input: bool) -> Exception | None:
    """Cek apakah format (kanal/dtype/48 kHz) diterima dalam mode Exclusive."""
    check = sd.check_input_settings if is_input else sd.check_output_settings
    try:
        check(device=dev.index, channels=channels, dtype=dtype, samplerate=SR,
              extra_settings=wasapi_settings(True))
        return None
    except Exception as exc:  # noqa: BLE001
        return exc


def try_duplex(dev_in, dev_out, in_ch: int, exclusive: bool, blocksize: int) -> dict:
    """Rekam + putar bersamaan 3 detik lewat callback, hitung status dropout."""
    counts = {"input_overflow": 0, "input_underflow": 0, "output_underflow": 0, "output_overflow": 0}

    def callback(indata, outdata, frames, t, status):
        outdata.fill(0)
        if status:
            for k in counts:
                if getattr(status, k):
                    counts[k] += 1

    result = {"ok": False}
    try:
        s_in = wasapi_settings(exclusive)
        with sd.Stream(device=(dev_in.index, dev_out.index), channels=(in_ch, 2), samplerate=SR,
                       dtype="float32", latency="low", blocksize=blocksize, extra_settings=(s_in, s_in),
                       callback=callback) as s:
            time.sleep(3.0)
            latency = s.latency
        result.update(ok=True, counts=counts, latency_ms=(latency[0] * 1000, latency[1] * 1000))
    except Exception as exc:  # noqa: BLE001
        result["error"] = exc
    return result


def report(label: str, res: dict) -> None:
    if res["ok"]:
        extra = ""
        if "peaks_db" in res:
            extra = "  puncak: " + ", ".join(f"kanal {i + 1} {p:.1f} dBFS" for i, p in enumerate(res["peaks_db"]))
        print(f"  [BERHASIL] {label}: {res['samplerate']:.0f} Hz, latensi {res['latency_ms']:.1f} ms{extra}")
    else:
        print(f"  [GAGAL]    {label}")
        print(f"             Pesan teknis: {res['error']}")
        print(f"             Artinya: {explain_error(res['error'])}")


def run_mode(dev_in, dev_out, exclusive: bool, blocksize: int) -> dict:
    mode = "WASAPI Exclusive" if exclusive else "WASAPI Shared"
    heading(f"{mode}: 48000 Hz, float32, buffer {blocksize}")
    summary = {"mode": mode, "inputs_ok": [], "output_ok": False, "duplex": None}
    for ch in (1, 2):
        if ch > dev_in.max_input_channels:
            print(f"  [LEWATI]   Input {ch} kanal: perangkat hanya punya {dev_in.max_input_channels} kanal input")
            continue
        res = try_input(dev_in, ch, exclusive, blocksize)
        report(f"Input {ch} kanal", res)
        if res["ok"]:
            summary["inputs_ok"].append(ch)
    res = try_output(dev_out, 2, exclusive, blocksize)
    report("Output 2 kanal", res)
    summary["output_ok"] = res["ok"]

    if summary["inputs_ok"] and summary["output_ok"]:
        in_ch = max(summary["inputs_ok"])
        res = try_duplex(dev_in, dev_out, in_ch, exclusive, blocksize)
        if res["ok"]:
            total = sum(res["counts"].values())
            lat_in, lat_out = res["latency_ms"]
            print(f"  [BERHASIL] Rekam {in_ch} kanal + putar 2 kanal bersamaan 3 detik: "
                  f"{total} dropout, latensi input {lat_in:.1f} ms / output {lat_out:.1f} ms")
            summary["duplex"] = total
        else:
            report(f"Rekam + putar bersamaan ({in_ch} kanal input)", res)
    return summary


def main() -> int:
    setup_console()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--device", default="SC202", help="kata kunci nama perangkat")
    parser.add_argument("--blocksize", type=int, default=devices.DEFAULT_BLOCKSIZE,
                        choices=devices.BLOCKSIZE_CHOICES)
    args = parser.parse_args()

    dev_in, dev_out = resolve_pair("wasapi", args.device)
    heading("Perangkat yang diuji")
    print(f"  Input : [{dev_in.index}] {dev_in.name} ({dev_in.max_input_channels} kanal, "
          f"format Windows saat ini {dev_in.default_samplerate:.0f} Hz)")
    print(f"  Output: [{dev_out.index}] {dev_out.name} ({dev_out.max_output_channels} kanal, "
          f"format Windows saat ini {dev_out.default_samplerate:.0f} Hz)")

    heading("Format yang diterima dalam mode Exclusive @ 48 kHz")
    for label, dev, is_input in (("Input", dev_in, True), ("Output", dev_out, False)):
        for ch in (1, 2):
            for dtype, name in (("int24", "24-bit"), ("float32", "float32")):
                err = check_format(dev, ch, dtype, is_input)
                status = "ya" if err is None else f"tidak ({err})"
                print(f"  {label} {ch} kanal {name:<8}: {status}")

    exclusive = run_mode(dev_in, dev_out, True, args.blocksize)
    results = [exclusive]
    if not (exclusive["inputs_ok"] and exclusive["output_ok"] and exclusive["duplex"] is not None):
        print("\n  Mode Exclusive tidak sepenuhnya berhasil, mencoba WASAPI Shared...")
        results.append(run_mode(dev_in, dev_out, False, args.blocksize))

    heading("KESIMPULAN")
    for r in results:
        inputs = ", ".join(str(c) for c in r["inputs_ok"]) or "tidak ada"
        print(f"  {r['mode']}: input yang bisa dibuka = {inputs} kanal; "
              f"output = {'ya' if r['output_ok'] else 'tidak'}; "
              f"rekam+putar = {'tidak diuji/gagal' if r['duplex'] is None else str(r['duplex']) + ' dropout'}")
    best = results[0]
    if 2 in best["inputs_ok"]:
        print("  -> 2 input bisa direkam terpisah (sesuai asumsi PRD).")
    elif 1 in best["inputs_ok"]:
        print("  -> HANYA 1 input yang bisa dibuka. Ini berbeda dari asumsi PRD (2 kanal).")
    print()
    ok = any(r["inputs_ok"] and r["output_ok"] and r["duplex"] == 0 for r in results)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
