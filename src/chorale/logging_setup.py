r"""Log aplikasi di %APPDATA%\HarmoniSATB\logs\ (dirotasi) dan penangkap error tak terduga.

Pengguna tidak pernah melihat traceback mentah: error tak terduga dicatat lengkap
di log, sedangkan layar hanya menampilkan pesan ramah.
"""

from __future__ import annotations

import faulthandler
import logging
import platform
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

from chorale import __version__
from chorale.appdirs import user_config_dir

LOG_FILE = "harmonisatb.log"
CRASH_FILE = "crash.log"
MAX_BYTES = 1_000_000
BACKUPS = 5

MSG_UNEXPECTED = ("Terjadi kesalahan yang tidak terduga. Rekaman dan proyek yang sudah tersimpan tetap aman.\n\n"
                  "Jika masalah berulang, kirimkan isi folder log kepada pengembang.")

log = logging.getLogger("chorale")
_crash_stream = None


def log_dir() -> Path:
    return user_config_dir() / "logs"


class _StreamToLog:
    """Pengganti stdout/stderr pada aplikasi tanpa konsol (PyInstaller windowed)."""

    def __init__(self, level: int):
        self.level = level

    def write(self, text: str) -> int:
        text = text.rstrip()
        if text:
            logging.getLogger("chorale.stdio").log(self.level, text)
        return len(text)

    def flush(self) -> None:
        pass


def setup_logging(level: int = logging.INFO) -> Path:
    """Siapkan log berotasi (1 MB x 5 file). Mengembalikan folder log."""
    global _crash_stream
    folder = log_dir()
    folder.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    if not any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        handler = RotatingFileHandler(folder / LOG_FILE, maxBytes=MAX_BYTES, backupCount=BACKUPS, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
        root.addHandler(handler)
        root.setLevel(level)
    if sys.stdout is None:
        sys.stdout = _StreamToLog(logging.INFO)
    if sys.stderr is None:
        sys.stderr = _StreamToLog(logging.ERROR)
    if _crash_stream is None:
        # Crash tingkat rendah (mis. di pustaka C) tetap tercatat.
        _crash_stream = open(folder / CRASH_FILE, "a", encoding="utf-8")
        faulthandler.enable(_crash_stream)
    log.info("HarmoniSATB Studio %s dimulai (Python %s, %s, frozen=%s)", __version__,
             platform.python_version(), platform.platform(), getattr(sys, "frozen", False))
    return folder


def install_exception_hooks(show_error) -> None:
    """Catat setiap exception yang tidak tertangani dan tampilkan pesan ramah lewat show_error()."""

    def handle(exc_type, exc, tb, where: str) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            return
        log.error("Error tak terduga (%s)", where, exc_info=(exc_type, exc, tb))
        try:
            show_error(MSG_UNEXPECTED)
        except Exception:  # noqa: BLE001 - jangan sampai penangkap error ikut gagal
            log.exception("Gagal menampilkan pesan error")

    sys.excepthook = lambda t, e, tb: handle(t, e, tb, "thread utama")
    threading.excepthook = lambda args: handle(args.exc_type, args.exc_value, args.exc_traceback,
                                               f"thread {args.thread.name if args.thread else '?'}")
