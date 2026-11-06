"""Layar Daftar Proyek (mockup: harmonisatb_studio_project_list)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from chorale.project.store import ProjectSummary, recent_summaries
from chorale.ui.theme import COLORS
from chorale.ui.widgets import StatusDots, TopBar, button, hbox, icon_label, label, vbox

CONTENT_WIDTH = 960


def format_date(iso: str) -> str:
    """'2026-11-06T13:05:44' -> '06-11-2026 13:05'."""
    try:
        return datetime.fromisoformat(iso).strftime("%d-%m-%Y %H:%M")
    except ValueError:
        return ""


class ProjectRow(QFrame):
    """Satu baris proyek (80 px) yang bisa diklik."""

    clicked = Signal(Path)

    def __init__(self, summary: ProjectSummary, parent=None):
        super().__init__(parent)
        self.summary = summary
        self.setObjectName("projectRow")
        self.setFixedHeight(80)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            f"QFrame#projectRow {{ background: {COLORS['panel']}; border: 1px solid {COLORS['border']}; "
            f"border-radius: 8px; }} QFrame#projectRow:hover {{ border: 1px solid {COLORS['blue']}; }}")
        title = label(summary.title, "rowTitle")
        title.setToolTip(summary.title)
        meta = label(f"{summary.tempo} BPM · {summary.time_signature}", "mono")
        left = vbox(title, 4, meta)
        left.setAlignment(Qt.AlignVCenter)

        date = label(format_date(summary.modified_at), "mono")
        chevron = icon_label("chevron_right", COLORS["text2"], 20)
        right = hbox(date, 24, chevron)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(24, 0, 24, 0)
        lay.setSpacing(16)
        lay.addLayout(left, 5)
        lay.addWidget(StatusDots(list(summary.recorded)), 0, Qt.AlignCenter)
        lay.addStretch(3)
        lay.addLayout(right)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit(self.summary.folder)
        super().mouseReleaseEvent(event)


class ProjectListScreen(QWidget):
    """Proyek Lagu: daftar proyek terakhir + Proyek Baru + Buka Proyek Lain…"""

    newProjectRequested = Signal()
    openFolderRequested = Signal()
    projectChosen = Signal(Path)
    settingsRequested = Signal()

    def __init__(self, recent_path: Path | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("screen")
        self._recent_path = recent_path

        bar = TopBar()
        bar.layout_.addWidget(icon_label("music", COLORS["text2"], 22))
        bar.layout_.addWidget(label("HarmoniSATB Studio", "appTitle"))
        bar.layout_.addStretch(1)
        settings_btn = button("Pengaturan", "toolbar", "gear", COLORS["text2"], 16)
        settings_btn.clicked.connect(self.settingsRequested)
        bar.layout_.addWidget(settings_btn)

        new_btn = button("Proyek Baru", "hero", "plus", "#FFFFFF", 22)
        new_btn.clicked.connect(self.newProjectRequested)
        heading = hbox(vbox(label("Proyek Lagu", "h1"), 8, label("Satu proyek untuk satu lagu.", "subtitle")),
                       None, new_btn)

        self._rows = QVBoxLayout()
        self._rows.setSpacing(12)
        self._empty = label("Belum ada proyek. Tekan Proyek Baru untuk mulai.", "secondary")

        other = button("Buka Proyek Lain…", "link")
        other.clicked.connect(self.openFolderRequested)

        column = QWidget()
        column.setObjectName("scrollContent")
        column.setFixedWidth(CONTENT_WIDTH)
        col = vbox(48, heading, 32, label("PROYEK TERAKHIR", "section"), 16, self._rows, self._empty, 24,
                   hbox(other, None), None)
        column.setLayout(col)

        holder = QWidget()
        holder.setObjectName("scrollContent")
        holder.setLayout(hbox(None, column, None, margins=(24, 0, 24, 24)))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(holder)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(bar)
        root.addWidget(scroll, 1)
        self.refresh()

    def refresh(self) -> None:
        """Muat ulang daftar dari recent.json."""
        while self._rows.count():
            item = self._rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        summaries = recent_summaries(self._recent_path)
        for s in summaries:
            row = ProjectRow(s)
            row.clicked.connect(self.projectChosen)
            self._rows.addWidget(row)
        self._empty.setVisible(not summaries)

    def row_count(self) -> int:
        return self._rows.count()
