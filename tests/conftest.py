"""Pengaturan bersama pytest."""

import pytest


@pytest.fixture(autouse=True)
def isolated_appdata(tmp_path, monkeypatch):
    """Arahkan %APPDATA% ke folder sementara agar tes tidak menyentuh kalibrasi/recent asli."""
    appdata = tmp_path / "appdata"
    monkeypatch.setenv("APPDATA", str(appdata))
    return appdata


def pytest_sessionfinish(session, exitstatus):
    """Hapus semua widget Qt sebelum interpreter keluar.

    Widget tanpa induk yang baru dihapus Python setelah QApplication hancur
    membuat proses crash saat keluar (kode 139), walau semua tes lulus.
    """
    try:
        import shiboken6
        from PySide6.QtCore import QThreadPool
        from PySide6.QtWidgets import QApplication
    except ImportError:
        return
    app = QApplication.instance()
    if app is None:
        return
    QThreadPool.globalInstance().waitForDone(10000)
    for widget in QApplication.topLevelWidgets():
        if shiboken6.isValid(widget):
            shiboken6.delete(widget)
    app.processEvents()
