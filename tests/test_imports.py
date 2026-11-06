"""Uji asap: semua paket proyek dan dependensi bisa di-import."""

import importlib

import pytest

MODULES = [
    "chorale",
    "chorale.audio",
    "chorale.project",
    "chorale.dsp",
    "chorale.ui",
    "sounddevice",
    "soundfile",
    "numpy",
    "scipy",
    "pedalboard",
    "pyloudnorm",
    "imageio_ffmpeg",
    "PySide6",
]


@pytest.mark.parametrize("name", MODULES)
def test_module_importable(name):
    importlib.import_module(name)


def test_ffmpeg_binary_available():
    import imageio_ffmpeg
    from pathlib import Path

    assert Path(imageio_ffmpeg.get_ffmpeg_exe()).is_file()
