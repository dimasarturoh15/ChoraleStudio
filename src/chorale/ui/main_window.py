"""Jendela utama 1440x900 dengan navigasi antar-layar (QStackedWidget)."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QMainWindow, QMessageBox, QStackedWidget, QWidget

from chorale.project import add_recent, open_project
from chorale.project.store import default_projects_dir
from chorale.settings import load_settings
from chorale.ui.new_project import NewProjectOverlay
from chorale.ui.processing import ProcessingOverlay
from chorale.ui.project_list import ProjectListScreen
from chorale.ui.recording_screen import RecordingScreen
from chorale.ui.result_screen import ResultScreen
from chorale.ui.settings_screen import SettingsScreen

log = logging.getLogger("chorale.ui")
WINDOW_SIZE = (1440, 900)
MIN_SIZE = (1280, 800)


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("HarmoniSATB Studio")
        self.resize(*WINDOW_SIZE)
        self.setMinimumSize(*MIN_SIZE)
        self.settings = load_settings()

        self.stack = QStackedWidget()
        self.projects = ProjectListScreen()
        self.settings_screen = SettingsScreen()
        self.recording = RecordingScreen()
        self.result_screen = ResultScreen()
        for w in (self.projects, self.settings_screen, self.recording, self.result_screen):
            self.stack.addWidget(w)
        self.setCentralWidget(self.stack)
        self._previous: QWidget = self.projects

        self.new_project = NewProjectOverlay(self.projects_dir(), self.stack)
        self.new_project.created.connect(self.open_folder)
        self.processing = ProcessingOverlay(self.stack)
        self.processing.finished.connect(self._produced)
        self.processing.cancelled.connect(self._produce_cancelled)
        self.processing.closed.connect(self._produce_closed)

        self.projects.newProjectRequested.connect(self.show_new_project)
        self.projects.openFolderRequested.connect(self.choose_project_folder)
        self.projects.projectChosen.connect(self.open_folder)
        self.projects.settingsRequested.connect(self.show_settings)
        self.settings_screen.closed.connect(self._back_from_settings)
        self.settings_screen.saved.connect(self._settings_saved)
        self.recording.backRequested.connect(self.show_projects)
        self.recording.settingsRequested.connect(self.show_settings)
        self.recording.produceRequested.connect(self._produce)
        self.result_screen.backRequested.connect(self._back_to_recording)
        self.result_screen.reprocessRequested.connect(self._produce)

    def projects_dir(self) -> Path:
        return Path(self.settings.projects_dir) if self.settings.projects_dir else default_projects_dir()

    # ----- navigasi -----
    def show_projects(self) -> None:
        self.recording.shutdown()
        self.projects.refresh()
        self.stack.setCurrentWidget(self.projects)

    def show_settings(self) -> None:
        self._previous = self.stack.currentWidget()
        if self._previous is self.recording:
            self.recording.suspend()
        self.settings_screen.open(self.settings)
        self.stack.setCurrentWidget(self.settings_screen)

    def _back_from_settings(self) -> None:
        self.stack.setCurrentWidget(self._previous)
        if self._previous is self.recording:
            self.recording.resume(self.settings)

    def _settings_saved(self, settings) -> None:
        self.settings = settings

    def show_new_project(self) -> None:
        self.new_project.projects_dir = self.projects_dir()
        self.new_project.open()

    def choose_project_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Buka Proyek Lain", str(self.projects_dir()))
        if folder:
            self.open_folder(Path(folder))

    def open_folder(self, folder: Path) -> None:
        try:
            project = open_project(folder)
        except FileNotFoundError:
            QMessageBox.warning(self, "Bukan folder proyek",
                                "Folder ini bukan proyek HarmoniSATB (tidak ada proyek.json).")
            return
        except Exception as exc:  # noqa: BLE001
            log.exception("Proyek tidak bisa dibuka: %s", folder)
            QMessageBox.warning(self, "Proyek tidak bisa dibuka", f"Proyek tidak bisa dibuka:\n{exc}")
            return
        add_recent(project)
        self.stack.setCurrentWidget(self.recording)
        self.recording.show_project(project, self.settings)

    # ----- proses produksi & hasil -----
    def _produce(self, project) -> None:
        """Lepaskan sound card, lalu jalankan produce() di dialog Memproses Produksi."""
        self.recording.suspend()
        self.result_screen.shutdown()
        self.processing.start(project)

    def _produced(self, result) -> None:
        self.result_screen.show_result(self.recording.project, result, self.settings)
        self.stack.setCurrentWidget(self.result_screen)

    def _resume_current(self, message: str | None = None) -> None:
        current = self.stack.currentWidget()
        if current is self.recording:
            self.recording.resume(self.settings)
            if message:
                self.recording.toast.show_message(message)
        elif current is self.result_screen:
            self.result_screen.show_result(self.recording.project, self.result_screen.result, self.settings)
            if message:
                self.result_screen.toast.show_message(message)

    def _produce_cancelled(self) -> None:
        self._resume_current("Proses dibatalkan. Tidak ada file yang disimpan.")

    def _produce_closed(self) -> None:
        if not self.processing.running:
            self._resume_current()

    def _back_to_recording(self) -> None:
        self.stack.setCurrentWidget(self.recording)
        self.recording.resume(self.settings)

    def closeEvent(self, event):
        if self.processing.running:
            self.processing.cancel()
            self.processing.worker.wait(30000)
        self.result_screen.shutdown()
        self.recording.shutdown()
        self.settings_screen.shutdown()
        super().closeEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape and self.new_project.isVisible():
            self.new_project.close_overlay()
        else:
            super().keyPressEvent(event)
