r"""Buat ikon aplikasi (not musik di kotak biru membulat) sebagai .ico multi-ukuran dan .png.

Hasil: src\chorale\ui\assets\harmonisatb.ico dan harmonisatb.png (dipakai jendela & installer).

Cara pakai:
    .venv\Scripts\python tools\make_icon.py
"""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath, QPen  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "chorale" / "ui" / "assets"
SIZES = (16, 24, 32, 48, 64, 128, 256)


def draw(size: int) -> QImage:
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    s = size / 256.0
    grad = QLinearGradient(0, 0, 0, size)
    grad.setColorAt(0, QColor("#4F8EF7"))
    grad.setColorAt(1, QColor("#2563EB"))
    p.setPen(Qt.NoPen)
    p.setBrush(grad)
    p.drawRoundedRect(QRectF(8 * s, 8 * s, 240 * s, 240 * s), 52 * s, 52 * s)

    # Dua not seperdelapan yang disambung balok, putih.
    white = QColor("#FFFFFF")
    p.setBrush(white)
    stem = max(1.5, 14 * s)
    p.setPen(QPen(white, stem, Qt.SolidLine, Qt.FlatCap))
    left_x, right_x = 98 * s, 178 * s
    p.drawLine(QPointF(left_x, 172 * s), QPointF(left_x, 70 * s))
    p.drawLine(QPointF(right_x, 152 * s), QPointF(right_x, 52 * s))
    beam = QPainterPath()
    beam.moveTo(left_x - stem / 2, 70 * s)
    beam.lineTo(right_x + stem / 2, 46 * s)
    beam.lineTo(right_x + stem / 2, 46 * s + 30 * s)
    beam.lineTo(left_x - stem / 2, 70 * s + 30 * s)
    beam.closeSubpath()
    p.setPen(Qt.NoPen)
    p.drawPath(beam)
    for cx, cy in ((left_x - 22 * s, 178 * s), (right_x - 22 * s, 158 * s)):
        p.save()
        p.translate(cx, cy)
        p.rotate(-20)
        p.drawEllipse(QRectF(-30 * s, -21 * s, 60 * s, 42 * s))
        p.restore()
    p.end()
    return img


def png_bytes(img: QImage) -> bytes:
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return bytes(data)


def write_ico(path: Path, images: list[QImage]) -> None:
    """Format ICO dengan entri PNG (didukung Windows Vista ke atas)."""
    blobs = [png_bytes(i) for i in images]
    header = struct.pack("<HHH", 0, 1, len(blobs))
    offset = 6 + 16 * len(blobs)
    entries = b""
    for img, blob in zip(images, blobs):
        w = img.width() if img.width() < 256 else 0
        entries += struct.pack("<BBBBHHII", w, w, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
    path.write_bytes(header + entries + b"".join(blobs))


def main() -> int:
    QGuiApplication(sys.argv)
    OUT.mkdir(parents=True, exist_ok=True)
    images = [draw(n) for n in SIZES]
    write_ico(OUT / "harmonisatb.ico", images)
    images[-1].save(str(OUT / "harmonisatb.png"))
    print(f"Ikon dibuat: {OUT / 'harmonisatb.ico'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
