"""Fungsi bantu bersama untuk skrip uji hardware di tools/."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from chorale.audio import device as devices  # noqa: E402  (harus sebelum import sounddevice)
from chorale.audio.device import DeviceInfo  # noqa: E402

import sounddevice as sd  # noqa: E402

HOSTAPI_ALIASES = {"wasapi": devices.HOSTAPI_WASAPI, "asio": devices.HOSTAPI_ASIO}

def setup_console() -> None:
    """Pastikan karakter non-ASCII pada nama perangkat tidak membuat skrip error."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass


def explain_error(exc: BaseException) -> str:
    """Terjemahkan error PortAudio ke penjelasan bahasa sederhana."""
    return devices.friendly_error(exc)


def heading(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def wasapi_settings(exclusive: bool) -> sd.WasapiSettings:
    return sd.WasapiSettings(exclusive=exclusive)


def resolve_pair(hostapi_alias: str, keyword: str) -> tuple[DeviceInfo, DeviceInfo]:
    """Cari pasangan input/output; keluar dengan pesan jelas jika tidak ada."""
    hostapi = HOSTAPI_ALIASES[hostapi_alias]
    if hostapi not in devices.hostapi_names():
        sys.exit(f"Host API '{hostapi}' tidak tersedia di komputer ini.")
    dev_in, dev_out = devices.find_io_pair(hostapi, keyword)
    if dev_in is None or dev_out is None:
        found = "input" if dev_in else ("output" if dev_out else "input maupun output")
        missing = "output" if dev_in else "input"
        sys.exit(
            f"Perangkat '{keyword}' di {hostapi} tidak lengkap/tidak ditemukan "
            f"({missing} tidak ada; yang ada: {found if dev_in or dev_out else 'tidak ada'}).\n"
            "Cek kabel USB sound card, lalu jalankan: .venv\\Scripts\\python tools\\list_devices.py"
        )
    return dev_in, dev_out


def add_device_args(parser, default_hostapi: str = "wasapi") -> None:
    """Argumen baris perintah bersama: perangkat, host API, mode, buffer."""
    parser.add_argument("--device", default="SC202",
                        help="kata kunci nama perangkat (default: SC202)")
    parser.add_argument("--hostapi", choices=sorted(HOSTAPI_ALIASES), default=default_hostapi,
                        help="host API (default: %(default)s)")
    parser.add_argument("--shared", action="store_true",
                        help="pakai WASAPI Shared, bukan Exclusive")
    parser.add_argument("--blocksize", type=int, default=devices.DEFAULT_BLOCKSIZE,
                        choices=devices.BLOCKSIZE_CHOICES, help="ukuran buffer (default: 256)")


def extra_settings_for(args) -> tuple | None:
    """extra_settings (input, output) untuk sounddevice sesuai argumen."""
    if args.hostapi != "wasapi":
        return None
    s = wasapi_settings(exclusive=not args.shared)
    return (s, s)


def mode_label(args) -> str:
    if args.hostapi == "asio":
        return "ASIO"
    return "WASAPI Shared" if args.shared else "WASAPI Exclusive"
