"""Buat/buka proyek, pemulihan take yatim, dan daftar proyek terakhir."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import soundfile as sf

from chorale.appdirs import user_config_dir, write_json_atomic
from chorale.project.model import (
    MASTER_DIR, PROJECT_FILE, STAMP_FORMAT, TAKE_FILE_RE, TAKES_DIR, TRACK_IDS, Project, Take, now_iso,
)

RECENT_FILE = "recent.json"
MAX_RECENT = 10
_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_folder_name(title: str) -> str:
    """Ubah judul lagu menjadi nama folder Windows yang aman."""
    name = _INVALID_CHARS.sub("_", title).strip().rstrip(". ")
    return name or "Proyek"


def create_project(parent: Path, title: str, **settings) -> Project:
    """Buat folder proyek baru (tidak pernah memakai folder yang sudah ada)."""
    project = Project(title=title, **settings)
    base = safe_folder_name(title)
    folder = Path(parent) / base
    n = 2
    while folder.exists():
        folder = Path(parent) / f"{base} ({n})"
        n += 1
    (folder / TAKES_DIR).mkdir(parents=True)
    (folder / MASTER_DIR).mkdir()
    project.folder = folder
    project.save()
    return project


def open_project(folder: Path) -> Project:
    """Buka proyek dari foldernya, lalu pulihkan take yang belum tercatat."""
    folder = Path(folder)
    path = folder / PROJECT_FILE
    if not path.is_file():
        raise FileNotFoundError(f"Folder ini bukan proyek HarmoniSATB (tidak ada {PROJECT_FILE}): {folder}")
    project = Project.from_dict(json.loads(path.read_text(encoding="utf-8")), folder=folder)
    (folder / TAKES_DIR).mkdir(exist_ok=True)
    (folder / MASTER_DIR).mkdir(exist_ok=True)
    if recover_orphan_takes(project):
        project.save()
    return project


def recover_orphan_takes(project: Project) -> list[Take]:
    """Daftarkan file take yang ada di takes/ tetapi belum tercatat di proyek.json.

    Ini terjadi jika aplikasi berhenti mendadak (listrik padam) saat merekam.
    Take seperti ini ditandai tidak lengkap dan tidak dijadikan take aktif.
    """
    known = {t.filename for tr in project.tracks.values() for t in tr.takes}
    recovered: list[Take] = []
    for f in sorted(project.takes_dir.glob("*.wav")):
        m = TAKE_FILE_RE.match(f.name)
        if not m or m["track"] not in TRACK_IDS or f.name in known:
            continue
        track = project.tracks[m["track"]]
        number = int(m["number"])
        if any(t.id == number for t in track.takes):
            continue
        try:
            duration = sf.info(str(f)).duration
        except RuntimeError:
            duration = 0.0
        recorded = datetime.strptime(m["stamp"], STAMP_FORMAT).isoformat(timespec="seconds")
        take = Take(id=number, filename=f.name, recorded_at=recorded, duration=duration, complete=False)
        track.takes.append(take)
        track.takes.sort(key=lambda t: t.id)
        recovered.append(take)
    return recovered


# ----- daftar proyek terakhir -----

def recent_file() -> Path:
    return user_config_dir() / RECENT_FILE


def _read_recent(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    try:
        return list(json.loads(path.read_text(encoding="utf-8")).get("projects", []))
    except (json.JSONDecodeError, AttributeError):
        return []


def add_recent(project: Project, path: Path | None = None) -> None:
    """Taruh proyek di urutan teratas daftar proyek terakhir (maks. 10)."""
    path = path or recent_file()
    folder = str(project.folder.resolve())
    entries = [e for e in _read_recent(path) if e.get("path") != folder]
    entries.insert(0, {"path": folder, "title": project.title, "opened_at": now_iso()})
    write_json_atomic(path, {"version": 1, "projects": entries[:MAX_RECENT]})


def list_recent(path: Path | None = None) -> list[dict]:
    """Daftar proyek terakhir yang foldernya masih ada."""
    return [e for e in _read_recent(path or recent_file())
            if (Path(e.get("path", "")) / PROJECT_FILE).is_file()]
