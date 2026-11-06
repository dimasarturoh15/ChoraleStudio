"""Jendela utama 1440x900 dengan navigasi antar-layar (QStackedWidget)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QMainWindow, QMessageBox, QStackedWidget, QWidget

from chorale.project import add_recent, open_project
from chorale.project.store import default_projects_dir
from chorale.settings import load_settings
from chorale.ui.new_project import NewProjectOverlay
from chorale.ui.project_list import ProjectListScreen
from chorale.ui.recording_screen import RecordingScreen
from chorale.ui.settings_screen import SettingsScreen

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
        for w in (self.projects, self.settings_screen, self.recording):
            self.stack.addWidget(w)
        self.setCentralWidget(self.stack)
        self._previous: QWidget = self.projects

        self.new_project = NewProjectOverlay(self.projects_dir(), self.stack)
        self.new_project.created.connect(self.open_folder)

        self.projects.newProjectRequested.connect(self.show_new_project)
        self.projects.openFolderRequested.connect(self.choose_project_folder)
        self.projects.projectChosen.connect(self.open_folder)
        self.projects.settingsRequested.connect(self.show_settings)
        self.settings_screen.closed.connect(self._back_from_settings)
        self.settings_screen.saved.connect(self._settings_saved)
        self.recording.backRequested.connect(self.show_projects)
        self.recording.settingsRequested.connect(self.show_settings)
        self.recording.produceRequested.connect(self._produce)

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
            QMessageBox.warning(self, "Proyek tidak bisa dibuka", f"Proyek tidak bisa dibuka:\n{exc}")
            return
        add_recent(project)
        self.stack.setCurrentWidget(self.recording)
        self.recording.show_project(project, self.settings)

    def _produce(self, project) -> None:
        self.recording.toast.show_message("Layar Proses Produksi & Master dibuat di Segmen 8. Untuk sekarang "
                                          "jalankan tools\\process_project.py.")

    def closeEvent(self, event):
        self.recording.shutdown()
        self.settings_screen.shutdown()
        super().closeEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape and self.new_project.isVisible():
            self.new_project.close_overlay()
        else:
            super().keyPressEvent(event)
