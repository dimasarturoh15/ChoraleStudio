"""Daftar komponen pihak ketiga dan lisensinya (halaman Tentang Aplikasi, installer)."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path


@dataclass(frozen=True)
class Component:
    name: str
    package: str | None   # nama distribusi untuk membaca versi; None = tidak dari pip
    license: str
    purpose: str


COMPONENTS = (
    Component("Qt for Python (PySide6)", "PySide6", "LGPL v3", "Antarmuka"),
    Component("PortAudio", None, "MIT", "Audio masuk/keluar (lewat sounddevice)"),
    Component("sounddevice", "sounddevice", "MIT", "Audio masuk/keluar"),
    Component("libsndfile", None, "LGPL v2.1", "Membaca/menulis WAV (lewat soundfile)"),
    Component("soundfile", "soundfile", "BSD 3-Clause", "Membaca/menulis WAV"),
    Component("NumPy", "numpy", "BSD 3-Clause", "Perhitungan audio"),
    Component("SciPy", "scipy", "BSD 3-Clause", "Filter & reverb"),
    Component("pedalboard (Spotify, memakai JUCE)", "pedalboard", "GPL v3", "EQ"),
    Component("pyloudnorm", "pyloudnorm", "MIT", "Pengukuran LUFS"),
    Component("FFmpeg (build gyan.dev)", None, "GPL v3", "MP3 & verifikasi ebur128"),
    Component("imageio-ffmpeg", "imageio-ffmpeg", "BSD 2-Clause", "Menyertakan FFmpeg"),
    Component("Font Inter", None, "SIL OFL 1.1", "Huruf antarmuka"),
    Component("Font JetBrains Mono", None, "SIL OFL 1.1", "Huruf angka"),
    Component("Python", None, "PSF License", "Bahasa pemrograman"),
)


def version_of(component: Component) -> str:
    if component.package is None:
        return ""
    try:
        return metadata.version(component.package)
    except metadata.PackageNotFoundError:
        return ""


def licenses_dir() -> Path | None:
    """Folder teks lisensi lengkap (ada di aplikasi hasil instal)."""
    if getattr(sys, "frozen", False):
        folder = Path(sys.executable).parent / "licenses"
        return folder if folder.is_dir() else None
    return None
