"""Tes Segmen 9: log berotasi, penangkap error, uji mandiri, halaman Tentang, berkas installer."""

import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from chorale import __version__  # noqa: E402
from chorale import logging_setup  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def fresh_logging(isolated_appdata):
    """Pasang log ke %APPDATA% sementara, lalu kembalikan keadaan logging & hook seperti semula."""
    root = logging.getLogger()
    before = list(root.handlers)
    hooks = (sys.excepthook, threading.excepthook)
    yield logging_setup.setup_logging()
    for h in root.handlers[:]:
        if h not in before:
            root.removeHandler(h)
            h.close()
    sys.excepthook, threading.excepthook = hooks


def test_version():
    assert __version__ == "1.3.0"
    assert 'version = "1.3.0"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def test_log_file_rotating_in_appdata(fresh_logging, isolated_appdata):
    folder = fresh_logging
    assert folder == isolated_appdata / "HarmoniSATB" / "logs"
    handler = next(h for h in logging.getLogger().handlers if isinstance(h, RotatingFileHandler))
    assert handler.maxBytes == 1_000_000 and handler.backupCount == 5
    logging.getLogger("chorale.test").warning("pesan uji")
    handler.flush()
    text = (folder / "harmonisatb.log").read_text(encoding="utf-8")
    assert "HarmoniSATB Studio 1.3.0 dimulai" in text and "pesan uji" in text


def test_unhandled_errors_are_logged_and_shown_friendly(fresh_logging):
    shown = []
    logging_setup.install_exception_hooks(shown.append)
    try:
        raise ValueError("rahasia teknis")
    except ValueError:
        sys.excepthook(*sys.exc_info())
    t = threading.Thread(target=lambda: 1 / 0, name="PekerjaUji")
    t.start()
    t.join()
    assert shown == [logging_setup.MSG_UNEXPECTED] * 2
    assert "Traceback" not in shown[0] and "rahasia teknis" not in shown[0]
    for h in logging.getLogger().handlers:
        h.flush()
    text = (fresh_logging / "harmonisatb.log").read_text(encoding="utf-8")
    assert "ValueError: rahasia teknis" in text and "ZeroDivisionError" in text and "PekerjaUji" in text


def test_selftest_passes(fresh_logging):
    from chorale.selftest import run_selftest

    assert run_selftest() == 0
    for h in logging.getLogger().handlers:
        h.flush()
    assert "Uji mandiri LULUS" in (fresh_logging / "harmonisatb.log").read_text(encoding="utf-8")


def test_about_page_lists_licenses():
    from PySide6.QtWidgets import QApplication, QLabel

    from chorale.licenses import COMPONENTS
    from chorale.ui import theme
    from chorale.ui.settings_screen import AboutPage

    app = QApplication.instance() or QApplication([])
    theme.apply(app)
    page = AboutPage()
    texts = {w.text() for w in page.findChildren(QLabel)}
    assert f"Versi {__version__}" in texts
    for comp in COMPONENTS:
        assert comp.name in texts and comp.license in texts
    assert {"LGPL v3", "GPL v3", "SIL OFL 1.1"} <= {c.license for c in COMPONENTS}
    assert page.logs_btn.text().strip() == "Buka Folder Log"


def test_installer_script_keeps_user_data():
    iss = (ROOT / "installer" / "HarmoniSATB.iss").read_text(encoding="utf-8")
    assert "{autoprograms}" in iss and "{autodesktop}" in iss
    assert "PrivilegesRequired=lowest" in iss
    assert "[UninstallDelete]" not in iss, "uninstall tidak boleh menghapus data pengguna"
    spec = (ROOT / "installer" / "harmonisatb.spec").read_text(encoding="utf-8")
    assert "console=False" in spec and "harmonisatb.ico" in spec
    assert (ROOT / "src" / "chorale" / "ui" / "assets" / "harmonisatb.ico").read_bytes()[:4] == b"\x00\x00\x01\x00"


def test_calibration_badge_for_varying_latency():
    """SC202HD: latensi berubah-ubah tidak ditampilkan sebagai error merah; ada saran atau penjelasan."""
    from PySide6.QtWidgets import QApplication

    from chorale.audio.calibration import CalibrationResult
    from chorale.settings import AppSettings
    from chorale.ui import theme
    from chorale.ui.settings_screen import HINT_VARIES_ENABLE, HINT_VARIES_HANDLED, AudioDevicePage

    app = QApplication.instance() or QApplication([])
    theme.apply(app)

    def result(spread):
        return CalibrationResult("in", "out", "Windows WASAPI", True, 48000, 256, 1008, 21.0,
                                 [1008, 1008 + spread], spread, 49.3, "2026-11-07T20:33:00")

    page = AudioDevicePage()
    page.load(AppSettings(sync_reference=True), cards=[])
    page._show_calibration(result(600))
    assert page.accuracy_badge.text() == "Berubah-ubah"
    assert page.calibration_hint.text() == HINT_VARIES_HANDLED and not page.calibration_hint.isHidden()

    page.reference_check.setChecked(False)
    page._show_calibration(result(600))
    assert page.accuracy_badge.text() == "Tidak konsisten"
    assert page.calibration_hint.text() == HINT_VARIES_ENABLE

    page._show_calibration(result(0))
    assert "Akurat" in page.accuracy_badge.text() and page.calibration_hint.isHidden()
