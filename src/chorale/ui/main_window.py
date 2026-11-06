"""Jendela utama 1440x900 dengan navigasi antar-layar (QStackedWidget)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QMainWindow, QMessageBox, QStackedWidget, QVBoxLayout, QWidget

from chorale.project import add_recent, open_project
from chorale.project.store import default_projects_dir
from chorale.settings import load_settings
from chorale.ui.new_project import NewProjectOverlay
from chorale.ui.project_list import ProjectListScreen
from chorale.ui.settings_screen import SettingsScreen
from chorale.ui.theme import COLORS
from chorale.ui.widgets import TopBar, button, label, vbox

WINDOW_SIZE = (1440, 900)
MIN_SIZE = (1280, 800)


class ProjectScreen(QWidget):
    """Sementara: layar rekam 5 track dibuat di Segmen 7."""

    def __init__(self, on_back, parent=None):
        super().__init__(parent)
        self.setObjectName("screen")
        bar = TopBar()
        back = button("", "square", "arrow_left", COLORS["text2"], 20)
        back.setToolTip("Kembali ke daftar proyek")
        back.clicked.connect(on_back)
        self.title = label("", "appTitle")
        bar.layout_.setSpacing(16)
        bar.layout_.addWidget(back)
        bar.layout_.addWidget(self.title)
        bar.layout_.addStretch(1)
        self.info = label("", "secondary")
        self.info.setWordWrap(True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(bar)
        lay.addLayout(vbox(self.info, None, margins=(48, 32, 48, 32)))

    def show_project(self, project) -> None:
        self.project = project
        self.title.setText(project.title)
        done = sum(1 for t in project.tracks.values() if t.has_audio)
        self.info.setText(f"{project.tempo} BPM · {project.time_signature} · {done} dari 5 track terekam.\n"
                          f"Folder: {project.folder}\n\nLayar rekam 5 track dibuat di Segmen 7.")


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
        self.project_screen = ProjectScreen(self.show_projects)
        for w in (self.projects, self.settings_screen, self.project_screen):
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

    def projects_dir(self) -> Path:
        return Path(self.settings.projects_dir) if self.settings.projects_dir else default_projects_dir()

    # ----- navigasi -----
    def show_projects(self) -> None:
        self.projects.refresh()
        self.stack.setCurrentWidget(self.projects)

    def show_settings(self) -> None:
        self._previous = self.stack.currentWidget()
        self.settings_screen.open(self.settings)
        self.stack.setCurrentWidget(self.settings_screen)

    def _back_from_settings(self) -> None:
        self.stack.setCurrentWidget(self._previous)

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
        self.project_screen.show_project(project)
        self.stack.setCurrentWidget(self.project_screen)

    def closeEvent(self, event):
        self.settings_screen.shutdown()
        super().closeEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape and self.new_project.isVisible():
            self.new_project.close_overlay()
        else:
            super().keyPressEvent(event)
