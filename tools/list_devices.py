"""Tampilkan semua host API dan perangkat audio, tandai SC202HD, dan cek ASIO.

Cara pakai:
    .venv\\Scripts\\python tools\\list_devices.py [--device SC202]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools._common import heading, setup_console  # noqa: E402
from chorale.audio import device as devices  # noqa: E402

import sounddevice as sd  # noqa: E402

MARK = "<<< SC202HD"


def installed_asio_drivers() -> list[str]:
    """Nama driver ASIO yang terdaftar di registry Windows (HKLM\\SOFTWARE\\ASIO)."""
    try:
        import winreg
    except ImportError:
        return []
    names: list[str] = []
    for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\ASIO", 0,
                                winreg.KEY_READ | view) as key:
                i = 0
                while True:
                    try:
                        names.append(winreg.EnumKey(key, i))
                    except OSError:
                        break
                    i += 1
        except OSError:
            continue
    return sorted(set(names))


def print_devices(keyword: str) -> list[devices.DeviceInfo]:
    all_devices = devices.list_devices()
    for api in devices.hostapi_names():
        heading(f"Host API: {api}")
        rows = [d for d in all_devices if d.hostapi == api]
        if not rows:
            print("  (tidak ada perangkat)")
            continue
        print(f"  {'No':>3}  {'In':>3} {'Out':>3}  {'SR default':>10}  Nama")
        for d in rows:
            mark = f"  {MARK}" if devices.matches_keyword(d.name, keyword) else ""
            print(f"  {d.index:>3}  {d.max_input_channels:>3} {d.max_output_channels:>3}  "
                  f"{d.default_samplerate:>8.0f} Hz  {d.name}{mark}")
    return all_devices


def print_target_summary(all_devices: list[devices.DeviceInfo], keyword: str) -> bool:
    heading(f"Ringkasan perangkat '{keyword}'")
    found = [d for d in all_devices if devices.matches_keyword(d.name, keyword)]
    if not found:
        print("  TIDAK DITEMUKAN. Windows belum melihat sound card ini.")
        print("  Coba: cabut-colok kabel USB, ganti port USB (langsung ke laptop, bukan hub),")
        print("  pastikan lampu sound card menyala, lalu cek Pengaturan > Sistem > Suara.")
        return False
    for api in devices.hostapi_names():
        dev_in, dev_out = devices.find_io_pair(api, keyword, all_devices)
        if dev_in is None and dev_out is None:
            continue
        parts = []
        if dev_in:
            parts.append(f"input {dev_in.max_input_channels} kanal (no. {dev_in.index})")
        if dev_out:
            parts.append(f"output {dev_out.max_output_channels} kanal (no. {dev_out.index})")
        print(f"  [tersedia] {api:<20} " + ", ".join(parts))
    return True


def print_asio_report() -> None:
    heading("Dukungan ASIO")
    lib = Path(getattr(sd, "_libname", "") or "").name or "(tidak diketahui)"
    print(f"  PortAudio yang dimuat : {lib}")
    print(f"  Versi PortAudio       : {sd.get_portaudio_version()[1]}")
    if devices.asio_build_loaded():
        print("  ASIO di PortAudio     : YA. sounddevice membawa build ber-ASIO,")
        print("                          aktif dengan variabel lingkungan SD_ENABLE_ASIO=1")
        print("                          (aplikasi menyetelnya otomatis di chorale.audio.devices).")
    else:
        print("  ASIO di PortAudio     : TIDAK. Build ber-ASIO tidak dimuat.")
        print("                          Setel SD_ENABLE_ASIO=1 sebelum sounddevice di-import.")
    drivers = installed_asio_drivers()
    if drivers:
        print(f"  Driver ASIO terpasang : {', '.join(drivers)}")
    else:
        print("  Driver ASIO terpasang : TIDAK ADA. ASIO baru bisa dipakai setelah driver ASIO")
        print("                          resmi sound card dipasang. Sampai itu, pakai WASAPI Exclusive.")


def main() -> int:
    setup_console()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--device", default="SC202", help="kata kunci nama perangkat")
    args = parser.parse_args()

    all_devices = print_devices(args.device)
    found = print_target_summary(all_devices, args.device)
    print_asio_report()
    print()
    return 0 if found else 1


if __name__ == "__main__":
    sys.exit(main())
