"""Lokasi folder konfigurasi pengguna dan penulisan file atomik."""

from __future__ import annotations

import json
import os
from pathlib import Path

APP_DIR_NAME = "HarmoniSATB"


def user_config_dir() -> Path:
    """Folder konfigurasi pengguna: %APPDATA%\\HarmoniSATB (atau ~/.harmonisatb)."""
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / APP_DIR_NAME
    return Path.home() / ".harmonisatb"


def write_json_atomic(path: Path, payload) -> None:
    """Tulis JSON ke file sementara, fsync, lalu ganti nama agar file tidak pernah setengah jadi."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
