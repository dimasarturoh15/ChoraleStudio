"""Titik masuk antarmuka grafis."""

from __future__ import annotations

import os
import sys

from chorale.audio import device  # noqa: F401  (aktifkan PortAudio ber-ASIO sebelum sounddevice dipakai)


def main(argv: list[str] | None = None) -> int:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from chorale.ui import theme
    from chorale.ui.main_window import MainWindow

    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("HarmoniSATB Studio")
    app.setOrganizationName("HarmoniSATB")
    theme.apply(app)
    window = MainWindow()
    window.show()
    auto_quit = os.environ.get("CHORALE_AUTOQUIT_MS")
    if auto_quit:
        QTimer.singleShot(int(auto_quit), window.close)
    return app.exec()
