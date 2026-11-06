"""Lapisan modal di dalam jendela: latar digelapkan + kartu di tengah."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QFrame, QWidget

from chorale.ui.theme import COLORS


class ModalOverlay(QWidget):
    closed = Signal()

    def __init__(self, parent: QWidget, card_width: int, accent: str | None = None):
        super().__init__(parent)
        self.card = QFrame(self)
        self.card.setObjectName("modal")
        top = f"border-top: 4px solid {accent};" if accent else ""
        self.card.setStyleSheet(f"QFrame#modal {{ background: {COLORS['panel']}; border: 1px solid "
                                f"{COLORS['border']}; border-radius: 12px; {top} }}")
        self.card.setFixedWidth(card_width)
        self.setFocusPolicy(Qt.StrongFocus)
        parent.installEventFilter(self)
        self.hide()

    def open(self) -> None:
        self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()
        self.recenter()
        self.setFocus()

    def close_overlay(self) -> None:
        self.hide()
        self.closed.emit()

    def recenter(self) -> None:
        self.card.adjustSize()
        self.card.move((self.width() - self.card.width()) // 2, (self.height() - self.card.height()) // 2)

    def eventFilter(self, obj, event):
        if obj is self.parentWidget() and event.type() == QEvent.Resize and self.isVisible():
            self.setGeometry(self.parentWidget().rect())
            self.recenter()
        return False

    def resizeEvent(self, event):
        self.recenter()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 165))
        p.end()

    def mousePressEvent(self, event):
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close_overlay()
        else:
            super().keyPressEvent(event)
