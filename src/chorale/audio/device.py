"""Perangkat audio: penemuan, pemilihan host API sesuai prioritas, dan stream duplex.

Modul ini mengaktifkan build PortAudio ber-ASIO bawaan sounddevice dengan
menyetel variabel lingkungan SD_ENABLE_ASIO sebelum sounddevice di-import.
Karena itu modul ini harus di-import sebelum modul lain meng-import sounddevice.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable

os.environ.setdefault("SD_ENABLE_ASIO", "1")

import sounddevice as sd  # noqa: E402

SAMPLE_RATE = 48000
DEFAULT_BLOCKSIZE = 256
BLOCKSIZE_CHOICES = (128, 256, 512, 1024)
TARGET_KEYWORDS = ("SC202", "SPL")

HOSTAPI_ASIO = "ASIO"
HOSTAPI_WASAPI = "Windows WASAPI"
HOSTAPI_PRIORITY = (HOSTAPI_ASIO, HOSTAPI_WASAPI)

MODE_ASIO = "asio"
MODE_EXCLUSIVE = "wasapi_exclusive"
MODE_SHARED = "wasapi_shared"
MODE_LABELS = {MODE_ASIO: "ASIO", MODE_EXCLUSIVE: "WASAPI Exclusive", MODE_SHARED: "WASAPI Shared"}

MSG_NOT_FOUND = (
    "Sound card tidak ditemukan. Pastikan kabel USB tercolok (sebaiknya langsung ke laptop, "
    "bukan lewat hub), lampu sound card menyala, dan perangkat muncul di Pengaturan > Sistem > Suara."
)
MSG_WRONG_RATE = (
    "Sound card tidak berjalan di 48 kHz (saat ini {rate:.0f} Hz). Cara memperbaiki: buka "
    "Pengaturan Suara Windows > pilih sound card > Properti > tab Advanced > pilih "
    "'24 bit, 48000 Hz (Studio Quality)', klik OK, lalu coba lagi. Lakukan untuk input dan output."
)
MSG_DEVICE_LOST = (
    "Sambungan ke sound card terputus (kabel USB tercabut?). Rekaman yang sudah masuk tetap "
    "tersimpan. Colokkan kembali sound card lalu tekan Rekam lagi."
)

# Pola pesan error PortAudio/WASAPI -> penjelasan sederhana + cara memperbaiki.
_ERROR_HINTS = [
    (("0x8889000a", "device in use", "-9985", "device unavailable"),
     "Sound card sedang dipakai aplikasi lain secara eksklusif, atau Windows tidak mengizinkan "
     "mode eksklusif. Tutup aplikasi audio lain (browser, Zoom, DAW, FxSound), lalu buka "
     "Pengaturan Suara Windows > perangkat > Properti > Advanced, centang "
     "'Allow applications to take exclusive control of this device'."),
    (("0x8889000e", "exclusive_mode_not_allowed"),
     "Windows melarang mode eksklusif untuk perangkat ini. Di Pengaturan Suara > Properti > "
     "Advanced, centang 'Allow applications to take exclusive control of this device'."),
    (("invalid sample rate", "-9997"),
     "Perangkat tidak mau dibuka di 48 kHz. Buka Pengaturan Suara Windows > perangkat > "
     "Properti > Advanced, pilih format '24 bit, 48000 Hz', lalu coba lagi."),
    (("0x88890008", "unsupported_format", "sample format not supported", "-9994"),
     "Format audio (jumlah kanal / bit / sample rate) ini tidak didukung perangkat dalam mode "
     "eksklusif."),
    (("invalid number of channels", "-9998"),
     "Jumlah kanal yang diminta tidak didukung perangkat dalam mode ini."),
    (("0x88890004", "device_invalidated", "-9988", "unanticipated host error"),
     MSG_DEVICE_LOST),
    (("invalid device", "-9996", "no device"), MSG_NOT_FOUND),
]


class AudioDeviceError(Exception):
    """Error perangkat audio dengan pesan yang bisa langsung ditampilkan ke pengguna."""

    def __init__(self, message: str, technical: str = ""):
        super().__init__(message)
        self.technical = technical


def friendly_error(exc: BaseException) -> str:
    """Terjemahkan error PortAudio ke penjelasan bahasa sederhana."""
    text = str(exc).lower()
    for patterns, hint in _ERROR_HINTS:
        if any(p in text for p in patterns):
            return hint
    return "Terjadi masalah pada sound card. Cabut-colok sound card lalu coba lagi."


@dataclass(frozen=True)
class DeviceInfo:
    """Ringkasan satu perangkat seperti dilaporkan PortAudio."""

    index: int
    name: str
    hostapi: str
    max_input_channels: int
    max_output_channels: int
    default_samplerate: float


@dataclass(frozen=True)
class DeviceSelection:
    """Perangkat yang dipilih untuk sesi audio."""

    hostapi: str
    input: DeviceInfo
    output: DeviceInfo
    exclusive: bool

    @property
    def mode(self) -> str:
        if self.hostapi == HOSTAPI_ASIO:
            return MODE_ASIO
        return MODE_EXCLUSIVE if self.exclusive else MODE_SHARED

    @property
    def mode_label(self) -> str:
        if self.hostapi == HOSTAPI_ASIO:
            return "ASIO"
        if self.hostapi == HOSTAPI_WASAPI:
            return "WASAPI Exclusive" if self.exclusive else "WASAPI Shared"
        return self.hostapi

    @property
    def input_channels(self) -> int:
        return min(2, self.input.max_input_channels)

    @property
    def output_channels(self) -> int:
        return min(2, self.output.max_output_channels)


def refresh_devices() -> None:
    """Muat ulang daftar perangkat PortAudio agar sound card yang baru dicolok terlihat.

    Semua stream harus sudah ditutup sebelum memanggil ini.
    """
    sd._terminate()
    sd._initialize()


def hostapi_names() -> list[str]:
    """Nama semua host API yang tersedia di build PortAudio yang dimuat."""
    return [h["name"] for h in sd.query_hostapis()]


def asio_build_loaded() -> bool:
    """True jika PortAudio yang dimuat adalah build ber-ASIO."""
    return HOSTAPI_ASIO in hostapi_names()


def list_devices() -> list[DeviceInfo]:
    """Daftar semua perangkat dari semua host API."""
    apis = hostapi_names()
    return [
        DeviceInfo(
            index=i,
            name=d["name"],
            hostapi=apis[d["hostapi"]],
            max_input_channels=d["max_input_channels"],
            max_output_channels=d["max_output_channels"],
            default_samplerate=d["default_samplerate"],
        )
        for i, d in enumerate(sd.query_devices())
    ]


def matches_keyword(name: str, keywords: tuple[str, ...] | str = TARGET_KEYWORDS) -> bool:
    """Cocokkan nama perangkat dengan kata kunci (tanpa membedakan huruf besar)."""
    if isinstance(keywords, str):
        keywords = (keywords,)
    lowered = name.lower()
    return any(k.lower() in lowered for k in keywords)


def find_io_pair(
    hostapi: str,
    keywords: tuple[str, ...] | str = TARGET_KEYWORDS,
    devices: list[DeviceInfo] | None = None,
) -> tuple[DeviceInfo | None, DeviceInfo | None]:
    """Cari perangkat input dan output yang cocok dalam satu host API.

    WASAPI memecah satu sound card menjadi perangkat input dan output terpisah,
    sedangkan ASIO biasanya satu perangkat dengan input dan output sekaligus.
    Jika ada beberapa kandidat, dipilih yang kanalnya paling banyak.
    """
    devices = list_devices() if devices is None else devices
    candidates = [d for d in devices if d.hostapi == hostapi and matches_keyword(d.name, keywords)]
    inputs = [d for d in candidates if d.max_input_channels > 0]
    outputs = [d for d in candidates if d.max_output_channels > 0]
    best_in = max(inputs, key=lambda d: d.max_input_channels, default=None)
    best_out = max(outputs, key=lambda d: d.max_output_channels, default=None)
    return best_in, best_out


@dataclass(frozen=True)
class SoundCard:
    """Satu sound card fisik, dengan mode driver yang tersedia untuknya."""

    name: str
    modes: tuple[str, ...]
    max_input_channels: int
    max_output_channels: int


def card_name(device_name: str) -> str:
    """Nama kartu dari nama perangkat WASAPI, mis. 'Microphone (SPL Audio SC202HD)' -> 'SPL Audio SC202HD'."""
    start, end = device_name.find("("), device_name.rfind(")")
    if 0 <= start < end:
        inner = device_name[start + 1:end].strip()
        if inner:
            return inner
    return device_name.strip()


def list_sound_cards(devices: list[DeviceInfo] | None = None) -> list[SoundCard]:
    """Sound card yang punya input DAN output di ASIO atau WASAPI, diurutkan menurut nama."""
    devices = list_devices() if devices is None else devices
    cards: dict[str, dict] = {}
    for d in devices:
        if d.hostapi not in (HOSTAPI_ASIO, HOSTAPI_WASAPI):
            continue
        name = card_name(d.name) if d.hostapi == HOSTAPI_WASAPI else d.name
        c = cards.setdefault(name, {"modes": set(), "in": {}, "out": {}})
        c["in"][d.hostapi] = max(c["in"].get(d.hostapi, 0), d.max_input_channels)
        c["out"][d.hostapi] = max(c["out"].get(d.hostapi, 0), d.max_output_channels)
    result = []
    for name, c in cards.items():
        modes = []
        if c["in"].get(HOSTAPI_ASIO) and c["out"].get(HOSTAPI_ASIO):
            modes.append(MODE_ASIO)
        if c["in"].get(HOSTAPI_WASAPI) and c["out"].get(HOSTAPI_WASAPI):
            modes += [MODE_EXCLUSIVE, MODE_SHARED]
        if modes:
            result.append(SoundCard(name, tuple(modes), max(c["in"].values()), max(c["out"].values())))
    target = [c for c in result if matches_keyword(c.name)]
    rest = sorted((c for c in result if not matches_keyword(c.name)), key=lambda c: c.name.lower())
    return target + rest


def _wasapi(exclusive: bool) -> sd.WasapiSettings:
    return sd.WasapiSettings(exclusive=exclusive)


def _accepts(selection: DeviceSelection) -> bool:
    """Cek tanpa membuka stream apakah 48 kHz float32 diterima perangkat."""
    extra = _extra_settings(selection)
    try:
        sd.check_input_settings(device=selection.input.index, channels=selection.input_channels,
                                dtype="float32", samplerate=SAMPLE_RATE,
                                extra_settings=extra[0] if extra else None)
        sd.check_output_settings(device=selection.output.index, channels=selection.output_channels,
                                 dtype="float32", samplerate=SAMPLE_RATE,
                                 extra_settings=extra[1] if extra else None)
        return True
    except Exception:  # noqa: BLE001 - PortAudioError/ValueError sama-sama berarti "tidak bisa"
        return False


def _extra_settings(selection: DeviceSelection):
    if selection.hostapi == HOSTAPI_WASAPI:
        s = _wasapi(selection.exclusive)
        return (s, s)
    return None


def select_device(
    keywords: tuple[str, ...] | str = TARGET_KEYWORDS,
    devices: list[DeviceInfo] | None = None,
    accepts: Callable[[DeviceSelection], bool] = _accepts,
    mode: str | None = None,
) -> DeviceSelection:
    """Pilih perangkat dengan urutan ASIO -> WASAPI Exclusive -> WASAPI Shared.

    mode: paksa satu mode (MODE_ASIO / MODE_EXCLUSIVE / MODE_SHARED); None = otomatis.
    Melempar AudioDeviceError dengan pesan ramah jika perangkat tidak ada atau
    tidak bisa berjalan di 48 kHz.
    """
    devices = list_devices() if devices is None else devices
    candidates: list[DeviceSelection] = []
    dev_in, dev_out = find_io_pair(HOSTAPI_ASIO, keywords, devices)
    if dev_in and dev_out:
        candidates.append(DeviceSelection(HOSTAPI_ASIO, dev_in, dev_out, exclusive=True))
    dev_in, dev_out = find_io_pair(HOSTAPI_WASAPI, keywords, devices)
    if dev_in and dev_out:
        candidates.append(DeviceSelection(HOSTAPI_WASAPI, dev_in, dev_out, exclusive=True))
        candidates.append(DeviceSelection(HOSTAPI_WASAPI, dev_in, dev_out, exclusive=False))
    if mode is not None:
        candidates = [c for c in candidates if c.mode == mode]
        if not candidates:
            raise AudioDeviceError(f"Mode {MODE_LABELS.get(mode, mode)} tidak tersedia untuk sound card ini.")
    if not candidates:
        raise AudioDeviceError(MSG_NOT_FOUND)

    for selection in candidates:
        if accepts(selection):
            return selection

    shared = candidates[-1]
    for dev in (shared.input, shared.output):
        if round(dev.default_samplerate) != SAMPLE_RATE:
            raise AudioDeviceError(MSG_WRONG_RATE.format(rate=dev.default_samplerate))
    raise AudioDeviceError(
        "Sound card ditemukan tetapi tidak bisa dibuka di 48 kHz. Tutup aplikasi audio lain, "
        "cabut-colok sound card, lalu coba lagi."
    )


def open_duplex_stream(
    selection: DeviceSelection,
    callback,
    blocksize: int = DEFAULT_BLOCKSIZE,
    finished_callback=None,
) -> sd.Stream:
    """Buka (belum dimulai) stream duplex 48 kHz float32 untuk perangkat terpilih."""
    if blocksize not in BLOCKSIZE_CHOICES:
        raise ValueError(f"Ukuran buffer harus salah satu dari {BLOCKSIZE_CHOICES}")
    try:
        return sd.Stream(
            device=(selection.input.index, selection.output.index),
            channels=(selection.input_channels, selection.output_channels),
            samplerate=SAMPLE_RATE,
            dtype="float32",
            latency="low",
            blocksize=blocksize,
            extra_settings=_extra_settings(selection),
            callback=callback,
            finished_callback=finished_callback,
        )
    except Exception as exc:  # noqa: BLE001
        raise AudioDeviceError(friendly_error(exc), technical=str(exc)) from exc
