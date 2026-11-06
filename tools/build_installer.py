r"""Build aplikasi (PyInstaller onedir) lalu installer (Inno Setup) jika ISCC tersedia.

Langkah:
  1. PyInstaller -> dist\HarmoniSATB Studio\
  2. Kumpulkan teks lisensi pihak ketiga -> dist\HarmoniSATB Studio\licenses\
  3. Uji jalan .exe dengan PATH tanpa Python (tutup otomatis setelah beberapa detik)
  4. Inno Setup -> installer\Output\HarmoniSATB-Studio-<versi>-Setup.exe

Cara pakai:
    .venv\Scripts\python tools\build_installer.py [--lewati-installer]
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from chorale import __version__  # noqa: E402
from chorale.licenses import COMPONENTS, version_of  # noqa: E402

NAME = "HarmoniSATB Studio"
DIST = ROOT / "dist" / NAME
EXE = DIST / f"{NAME}.exe"
ISS = ROOT / "installer" / "HarmoniSATB.iss"
LICENSE_PACKAGES = ("PySide6", "PySide6_Essentials", "shiboken6", "sounddevice", "soundfile", "numpy", "scipy",
                    "pedalboard", "pyloudnorm", "imageio-ffmpeg", "cffi", "pycparser")
ISCC_CANDIDATES = (
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe",
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Inno Setup 6" / "ISCC.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
)

FFMPEG_NOTICE = """FFmpeg
======
Aplikasi ini menyertakan program FFmpeg (build "essentials" dari gyan.dev, lewat paket imageio-ffmpeg)
untuk membuat MP3 dan mengukur kelantangan (filter ebur128).

Build ini berlisensi GNU General Public License versi 3 (GPL v3).
Kode sumber FFmpeg: https://ffmpeg.org/download.html
Informasi build:     https://www.gyan.dev/ffmpeg/builds/
Teks GPL v3:          lihat licenses/pedalboard/LICENSE (teks lisensi yang sama) atau https://www.gnu.org/licenses/gpl-3.0.html
"""


def run_pyinstaller() -> None:
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                    "--distpath", str(ROOT / "dist"), "--workpath", str(ROOT / "build" / "pyinstaller"),
                    str(ROOT / "installer" / "harmonisatb.spec")], check=True, cwd=ROOT)


def collect_licenses() -> Path:
    target = DIST / "licenses"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir()
    for package in LICENSE_PACKAGES:
        try:
            dist = metadata.distribution(package)
        except metadata.PackageNotFoundError:
            continue
        for f in dist.files or []:
            name = Path(str(f)).name.upper()
            if any(key in name for key in ("LICENSE", "COPYING", "NOTICE")):
                src = Path(dist.locate_file(f))
                if src.is_file():
                    dest = target / package / Path(str(f)).name
                    dest.parent.mkdir(exist_ok=True)
                    if dest.exists():
                        dest = dest.with_name(f"{dest.stem}_{len(list(dest.parent.iterdir()))}{dest.suffix}")
                    shutil.copyfile(src, dest)
    fonts = ROOT / "src" / "chorale" / "ui" / "fonts"
    (target / "fonts").mkdir()
    for f in fonts.glob("*.txt"):
        shutil.copyfile(f, target / "fonts" / f.name)
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.is_file():
        (target / "Python").mkdir()
        shutil.copyfile(python_license, target / "Python" / "LICENSE.txt")
    (target / "FFmpeg").mkdir()
    (target / "FFmpeg" / "README.txt").write_text(FFMPEG_NOTICE, encoding="utf-8")
    lines = [f"HarmoniSATB Studio {__version__} — komponen pihak ketiga", "=" * 60, ""]
    for comp in COMPONENTS:
        ver = version_of(comp)
        lines.append(f"- {comp.name}{' ' + ver if ver else ''}: {comp.license} ({comp.purpose})")
    lines += ["", "Teks lisensi lengkap ada di subfolder folder ini."]
    (target / "THIRD_PARTY_NOTICES.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def folder_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def clean_env() -> dict:
    """Lingkungan tanpa Python di PATH (meniru laptop yang tidak punya Python)."""
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join(p for p in env.get("PATH", "").split(os.pathsep)
                                  if "python" not in p.lower() and ".venv" not in p.lower())
    for key in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV"):
        env.pop(key, None)
    return env


def smoke_test(exe: Path, seconds: float = 5.0) -> int:
    """Buka .exe (menutup diri setelah beberapa detik), lalu jalankan --uji-mandiri (produce sampai ekspor)."""
    env = clean_env()
    env["CHORALE_AUTOQUIT_MS"] = str(int(seconds * 1000))
    start = time.monotonic()
    proc = subprocess.run([str(exe)], env=env, cwd=str(exe.parent), timeout=300)
    print(f"  Buka & tutup jendela: kode keluar {proc.returncode} setelah {time.monotonic() - start:.1f} detik")
    if proc.returncode != 0:
        return proc.returncode
    start = time.monotonic()
    proc = subprocess.run([str(exe), "--uji-mandiri"], env=clean_env(), cwd=str(exe.parent), timeout=300)
    print(f"  Uji mandiri (5 track -> WAV/MP3/laporan): kode keluar {proc.returncode} "
          f"setelah {time.monotonic() - start:.1f} detik")
    return proc.returncode


def find_iscc() -> Path | None:
    found = shutil.which("ISCC")
    if found:
        return Path(found)
    return next((p for p in ISCC_CANDIDATES if p.is_file()), None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lewati-installer", action="store_true", help="hanya build PyInstaller")
    args = parser.parse_args()

    print(f"1. PyInstaller ({NAME} {__version__})")
    run_pyinstaller()
    print("2. Lisensi pihak ketiga")
    collect_licenses()
    size = folder_size(DIST)
    print(f"   Ukuran folder aplikasi: {size / 1024**2:.0f} MB ({sum(1 for _ in DIST.rglob('*'))} file)")
    print("3. Uji jalan tanpa Python di PATH")
    if smoke_test(EXE) != 0:
        print("   GAGAL: aplikasi tidak keluar dengan normal. Lihat %APPDATA%\\HarmoniSATB\\logs\\")
        return 1
    if args.lewati_installer:
        return 0
    print("4. Inno Setup")
    iscc = find_iscc()
    if iscc is None:
        print("   ISCC.exe (Inno Setup 6) tidak ditemukan. Pasang Inno Setup 6 dari https://jrsoftware.org/isdl.php,")
        print("   lalu jalankan ulang skrip ini.")
        return 2
    subprocess.run([str(iscc), f"/DMyAppVersion={__version__}", str(ISS)], check=True, cwd=ROOT / "installer")
    setup = next((ROOT / "installer" / "Output").glob("*Setup.exe"))
    print(f"   Installer: {setup} ({setup.stat().st_size / 1024**2:.0f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
