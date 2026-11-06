# -*- mode: python ; coding: utf-8 -*-
# Spec PyInstaller (onedir, tanpa konsol). Jalankan lewat tools\build_installer.py.
from pathlib import Path

from PyInstaller.utils.hooks import collect_dynamic_libs, copy_metadata

ROOT = Path(SPECPATH).parent
UI = ROOT / "src" / "chorale" / "ui"
NAME = "HarmoniSATB Studio"

datas = [
    (str(UI / "style.qss"), "chorale/ui"),
    (str(UI / "fonts"), "chorale/ui/fonts"),
    (str(UI / "assets"), "chorale/ui/assets"),
]
# Metadata paket agar halaman "Tentang Aplikasi" bisa menampilkan versinya.
for package in ("PySide6", "sounddevice", "soundfile", "numpy", "scipy", "pedalboard", "pyloudnorm",
                "imageio-ffmpeg"):
    datas += copy_metadata(package)

# PortAudio (termasuk build ber-ASIO) dan libsndfile.
binaries = collect_dynamic_libs("sounddevice") + collect_dynamic_libs("soundfile")

a = Analysis(
    [str(ROOT / "installer" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=["chorale.ui.app"],
    excludes=["tkinter", "matplotlib", "IPython", "pytest", "PyQt5", "PyQt6", "pandas",
              "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQuick", "PySide6.QtQml",
              "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtDataVisualization",
              "PySide6.QtPdf", "PySide6.QtNetwork", "PySide6.QtOpenGL", "PySide6.QtSql", "PySide6.QtTest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=NAME,
    console=False,
    icon=str(UI / "assets" / "harmonisatb.ico"),
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name=NAME, upx=False)
