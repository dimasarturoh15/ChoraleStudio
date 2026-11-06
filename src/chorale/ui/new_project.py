"""Dialog Proyek Baru (mockup: harmonisatb_studio_new_project_modal).

Ditampilkan sebagai lapisan di atas jendela utama (latar digelapkan), bukan
jendela terpisah, agar sama dengan mockup.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QPainter
from PySide6.QtWidgets import QFileDialog, QFrame, QGridLayout, QLineEdit, QVBoxLayout, QWidget

from chorale.project import create_project
from chorale.project.model import TEMPO_MAX, TEMPO_MIN, TIME_SIGNATURES
from chorale.project.store import documents_dir, safe_folder_name
from chorale.ui.theme import COLORS
from chorale.ui.widgets import (
    SegmentedControl, Stepper, ToggleSwitch, button, hbox, label, refresh_style, vbox,
)

MSG_EMPTY_TITLE = "Judul lagu tidak boleh kosong."


class NewProjectOverlay(QWidget):
    """Lapisan modal: isi judul, tempo, birama, hitungan awal, metronom."""

    created = Signal(Path)
    closed = Signal()

    CARD_WIDTH = 640

    def __init__(self, projects_dir: Path, parent: QWidget):
        super().__init__(parent)
        self.projects_dir = Path(projects_dir)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setFocusPolicy(Qt.StrongFocus)

        self.card = QFrame(self)
        self.card.setObjectName("modal")
        self.card.setStyleSheet(f"QFrame#modal {{ background: {COLORS['panel']}; border: 1px solid "
                                f"{COLORS['border']}; border-radius: 12px; }}")
        self.card.setFixedWidth(self.CARD_WIDTH)

        close = button("", "icon", "close", COLORS["text2"], 22)
        close.setToolTip("Tutup")
        close.clicked.connect(self.close_overlay)
        header = hbox(label("Proyek Baru", "h1"), None, close)

        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Contoh: Bapa Engkau Sungguh Baik")
        self.title_edit.textChanged.connect(self._on_title_changed)
        self.error = label(MSG_EMPTY_TITLE, "error")
        self.error.hide()
        self.location = label("", "hint")
        self.location.setWordWrap(False)
        change = button("Ubah…", "link")
        change.setStyleSheet("font-size: 13px;")
        change.clicked.connect(self._choose_folder)

        self.tempo = Stepper(72, TEMPO_MIN, TEMPO_MAX)
        self.time_signature = SegmentedControl([(ts, ts) for ts in TIME_SIGNATURES], mono=True)
        self.time_signature.set_value("4/4")
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(6)
        grid.addWidget(label("Tempo (BPM)", "field"), 0, 0)
        grid.addWidget(label("Birama", "field"), 0, 1)
        grid.addWidget(self.tempo, 1, 0)
        grid.addWidget(self.time_signature, 1, 1)
        grid.addWidget(label(f"{TEMPO_MIN} – {TEMPO_MAX}", "hintMono"), 2, 0)

        self.count_in = SegmentedControl([(0, "Tanpa"), (1, "1 Bar"), (2, "2 Bar")], height=44)
        self.count_in.set_value(2)
        self.metronome = ToggleSwitch(True)
        metro_label = label("Metronom tetap bunyi setelah hitungan awal", "body")

        cancel = button("Batal", "secondary")
        cancel.clicked.connect(self.close_overlay)
        self.create_btn = button("Buat Proyek", "primary")
        self.create_btn.setDefault(True)
        self.create_btn.clicked.connect(self.submit)

        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(40, 36, 40, 40)
        lay.setSpacing(0)
        lay.addLayout(header)
        lay.addSpacing(20)
        lay.addLayout(vbox(label("Judul Lagu", "field"), 6, self.title_edit, 6, self.error,
                           hbox(self.location, 6, change, None)))
        lay.addSpacing(20)
        lay.addLayout(grid)
        lay.addSpacing(24)
        lay.addLayout(vbox(label("Hitungan Awal", "field"), 6, self.count_in))
        lay.addSpacing(24)
        lay.addLayout(hbox(metro_label, None, self.metronome))
        lay.addSpacing(6)
        lay.addWidget(label("Matikan untuk lagu bertempo bebas.", "hint"))
        lay.addSpacing(32)
        lay.addLayout(hbox(None, cancel, 12, self.create_btn))

        self._update_location()
        parent.installEventFilter(self)
        self.hide()

    # ----- tampilan -----
    def open(self) -> None:
        self.title_edit.clear()
        self._set_invalid(False)
        self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()
        self._center()
        self.title_edit.setFocus()

    def close_overlay(self) -> None:
        self.hide()
        self.closed.emit()

    def eventFilter(self, obj, event):
        if obj is self.parentWidget() and event.type() == QEvent.Resize and self.isVisible():
            self.setGeometry(self.parentWidget().rect())
            self._center()
        return False

    def resizeEvent(self, event):
        self._center()

    def _center(self) -> None:
        self.card.adjustSize()
        self.card.move((self.width() - self.card.width()) // 2, (self.height() - self.card.height()) // 2)

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 165))
        p.end()

    def mousePressEvent(self, event):
        event.accept()  # klik di luar kartu tidak menembus ke layar di bawahnya

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Escape:
            self.close_overlay()
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.submit()
        else:
            super().keyPressEvent(event)

    # ----- isian -----
    def _on_title_changed(self, _text: str) -> None:
        if self.title_edit.property("invalid") and self.title_edit.text().strip():
            self._set_invalid(False)
        self._update_location()

    def _set_invalid(self, invalid: bool) -> None:
        self.title_edit.setProperty("invalid", invalid)
        refresh_style(self.title_edit)
        self.error.setVisible(invalid)
        self._center()

    def _update_location(self) -> None:
        name = safe_folder_name(self.title_edit.text()) if self.title_edit.text().strip() else "<judul>"
        full = self.projects_dir / name
        try:
            shown = str(Path("Documents") / full.relative_to(documents_dir()))
        except ValueError:
            shown = str(full)
        text = f"Disimpan di {shown}"
        available = self.CARD_WIDTH - 80 - 70  # lebar kartu - margin - tombol "Ubah…"
        metrics = self.location.fontMetrics()
        if metrics.horizontalAdvance(text) > available:
            text = metrics.elidedText(text, Qt.ElideMiddle, available)
        self.location.setText(text)
        self.location.setToolTip(str(full))

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Pilih folder penyimpanan proyek", str(self.projects_dir))
        if folder:
            self.projects_dir = Path(folder)
            self._update_location()

    def values(self) -> dict:
        return {
            "title": self.title_edit.text().strip(),
            "tempo": self.tempo.value(),
            "time_signature": self.time_signature.value(),
            "count_in_bars": self.count_in.value(),
            "metronome_after_count_in": self.metronome.isChecked(),
        }

    def submit(self) -> Path | None:
        """Validasi lalu buat folder proyek. Mengembalikan folder baru (atau None jika tidak valid)."""
        v = self.values()
        if not v["title"]:
            self._set_invalid(True)
            self.title_edit.setFocus()
            return None
        if not (TEMPO_MIN <= v["tempo"] <= TEMPO_MAX):
            return None
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        project = create_project(self.projects_dir, v.pop("title"), **v)
        self.hide()
        self.created.emit(project.folder)
        return project.folder
