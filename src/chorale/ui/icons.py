"""Ikon garis sederhana (digambar sendiri, viewBox 24x24) yang dirender lewat QtSvg."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_PATHS = {
    "music": '<path d="M9 17V5l11-2v12"/><circle cx="6" cy="17" r="3"/><circle cx="17" cy="15" r="3"/>',
    "gear": '<circle cx="12" cy="12" r="3"/><circle cx="12" cy="12" r="7"/>'
            '<path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1l2.1-2.1M17 7l2.1-2.1"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "chevron_right": '<path d="M9 6l6 6-6 6"/>',
    "chevron_down": '<path d="M6 9l6 6 6-6"/>',
    "arrow_left": '<path d="M19 12H5M11 6l-6 6 6 6"/>',
    "lock": '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
    "timer": '<circle cx="12" cy="13" r="8"/><path d="M12 9v4l2.5 2.5M10 2h4"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7"/>',
    "close": '<path d="M6 6l12 12M18 6L6 18"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
}


def svg(name: str, color: str, stroke: float = 2.0) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{_PATHS[name]}</svg>')


def pixmap(name: str, color: str, size: int, stroke: float = 2.0, ratio: float = 2.0) -> QPixmap:
    """Pixmap ikon tajam pada layar HiDPI (digambar 2x lalu ditandai devicePixelRatio)."""
    renderer = QSvgRenderer(QByteArray(svg(name, color, stroke).encode()))
    pm = QPixmap(int(size * ratio), int(size * ratio))
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size * ratio, size * ratio))
    painter.end()
    pm.setDevicePixelRatio(ratio)
    return pm


def icon(name: str, color: str, size: int = 20, stroke: float = 2.0) -> QIcon:
    return QIcon(pixmap(name, color, size, stroke))
