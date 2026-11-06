"""Titik masuk antarmuka grafis."""

from __future__ import annotations

import logging
import os
import sys

from chorale.audio import device  # noqa: F401  (aktifkan PortAudio ber-ASIO sebelum sounddevice dipakai)
from chorale.logging_setup import install_exception_hooks, log_dir, setup_logging

log = logging.getLogger("chorale.ui")


def open_folder(path) -> None:
    os.startfile(str(path))  # noqa: S606 - membuka folder di Windows Explorer


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    if "--uji-mandiri" in (argv if argv is not None else sys.argv):
        from chorale.selftest import run_selftest

        return run_selftest()

    from PySide6.QtCore import QObject, QTimer, Signal, qInstallMessageHandler
    from PySide6.QtWidgets import QApplication, QMessageBox

    from chorale.ui import theme
    from chorale.ui.main_window import MainWindow

    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("HarmoniSATB Studio")
    app.setOrganizationName("HarmoniSATB")
    from pathlib import Path

    from PySide6.QtGui import QIcon

    app.setWindowIcon(QIcon(str(Path(theme.UI_DIR) / "assets" / "harmonisatb.ico")))

    class ErrorReporter(QObject):
        """Pesan error dari thread mana pun ditampilkan di thread UI lewat sinyal."""

        message = Signal(str)

    reporter = ErrorReporter()
    shown = {"open": False}

    def show_dialog(text: str) -> None:
        if shown["open"]:  # jangan menumpuk dialog yang sama
            return
        shown["open"] = True
        box = QMessageBox(QMessageBox.Warning, "Terjadi kesalahan", text, parent=app.activeWindow())
        folder_btn = box.addButton("Buka Folder Log", QMessageBox.ActionRole)
        box.addButton("Tutup", QMessageBox.AcceptRole)
        box.exec()
        shown["open"] = False
        if box.clickedButton() is folder_btn:
            open_folder(log_dir())

    reporter.message.connect(show_dialog)
    install_exception_hooks(reporter.message.emit)

    qt_log = logging.getLogger("chorale.qt")
    qInstallMessageHandler(lambda mode, context, text: qt_log.warning("%s", text))

    theme.apply(app)
    window = MainWindow()
    window.show()
    # Muat modul DSP (scipy, pedalboard: lambat diimpor) di latar setelah jendela tampil,
    # agar tombol "Proses Produksi & Master" tidak menunggu import.
    import threading

    def prewarm() -> None:
        try:
            import chorale.dsp.produce  # noqa: F401
        except Exception:  # noqa: BLE001
            log.exception("Gagal memuat modul DSP di latar")

    QTimer.singleShot(3000, lambda: threading.Thread(target=prewarm, name="MuatDSP", daemon=True).start())
    auto_quit = os.environ.get("CHORALE_AUTOQUIT_MS")
    if auto_quit:
        QTimer.singleShot(int(auto_quit), window.close)
    code = app.exec()
    log.info("Aplikasi ditutup (kode %s)", code)
    # Hapus jendela selagi QApplication masih hidup; urutan penghapusan otomatis Python
    # saat keluar tidak pasti dan bisa membuat Qt crash (mis. popup QComboBox).
    import shiboken6

    shiboken6.delete(window)
    return code
