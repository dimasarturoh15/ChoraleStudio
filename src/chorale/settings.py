"""Pengaturan aplikasi milik pengguna: %APPDATA%\\HarmoniSATB\\settings.json."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from chorale.appdirs import user_config_dir, write_json_atomic

SETTINGS_FILE = "settings.json"

DRIVER_MODES = ("asio", "wasapi_exclusive", "wasapi_shared")
INSTRUMENT_INPUTS = ("1-2", "1", "2")  # 1-2 = stereo, 1/2 = mono dari input itu
VOCAL_INPUTS = ("1", "2")


@dataclass
class AppSettings:
    device_name: str | None = None      # nama sound card; None = cari SC202HD otomatis
    driver_mode: str | None = None      # None = otomatis (ASIO -> WASAPI Exclusive -> Shared)
    blocksize: int = 256
    instrument_input: str = "1-2"
    vocal_input: str = "1"
    projects_dir: str | None = None     # None = Documents\HarmoniSATB
    metronome_volume: int = 80          # persen; 100% = 0 dB
    sync_reference: bool = False        # kabel Output -> input lain sebagai kanal acuan saat merekam vokal

    def metronome_volume_db(self) -> float:
        return 20 * math.log10(max(self.metronome_volume, 1) / 100)

    def instrument_channels(self) -> tuple[int, int]:
        """(kanal pertama berbasis 0, jumlah kanal) untuk merekam piano."""
        if self.instrument_input == "1-2":
            return 0, 2
        return int(self.instrument_input) - 1, 1

    def vocal_channel(self) -> int:
        return int(self.vocal_input) - 1

    def reference_channel(self) -> int | None:
        """Kanal acuan (berbasis 0) untuk take vokal: input yang tidak dipakai mikrofon; None jika mati."""
        return 1 - self.vocal_channel() if self.sync_reference else None


def settings_path() -> Path:
    return user_config_dir() / SETTINGS_FILE


def load_settings(path: Path | None = None) -> AppSettings:
    """Baca pengaturan; nilai yang hilang atau tidak valid diganti bawaan."""
    path = path or settings_path()
    defaults = AppSettings()
    if not path.is_file():
        return defaults
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return defaults
    known = {f.name for f in fields(AppSettings)}
    s = AppSettings(**{k: v for k, v in data.items() if k in known})
    if s.driver_mode not in (None, *DRIVER_MODES):
        s.driver_mode = None
    if s.blocksize not in (128, 256, 512, 1024):
        s.blocksize = defaults.blocksize
    if s.instrument_input not in INSTRUMENT_INPUTS:
        s.instrument_input = defaults.instrument_input
    if s.vocal_input not in VOCAL_INPUTS:
        s.vocal_input = defaults.vocal_input
    if not isinstance(s.metronome_volume, int) or not 0 <= s.metronome_volume <= 100:
        s.metronome_volume = defaults.metronome_volume
    if not isinstance(s.sync_reference, bool):
        s.sync_reference = defaults.sync_reference
    return s


def save_settings(settings: AppSettings, path: Path | None = None) -> None:
    write_json_atomic(path or settings_path(), asdict(settings))
