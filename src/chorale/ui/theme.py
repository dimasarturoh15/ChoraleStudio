"""Token desain (warna, font, radius) dari mockup design/, plus pemuat font & stylesheet."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from chorale.ui import icons

UI_DIR = Path(__file__).resolve().parent
FONT_DIR = UI_DIR / "fonts"
QSS_FILE = UI_DIR / "style.qss"

COLORS = {
    "app": "#0E1116",
    "panel": "#161B22",
    "raised": "#1F2630",
    "border": "#2A3340",
    "text": "#E6EDF3",
    "text2": "#8B98A5",
    "blue": "#3B82F6",
    "blue_hover": "#2563EB",
    "green": "#22C55E",
    "yellow": "#EAB308",
    "red": "#EF4444",
    "gray": "#4B5563",
}

TRACK_COLORS = {
    "piano": "#14B8A6",
    "bass": "#8B5CF6",
    "tenor": "#3B82F6",
    "alto": "#F59E0B",
    "sopran": "#EF4444",
}

RADIUS_SM, RADIUS, RADIUS_LG = 4, 6, 8
MIN_FONT_PX = 13

FALLBACK_UI = "Segoe UI"
FALLBACK_MONO = "Consolas"
_families = {"ui": FALLBACK_UI, "mono": FALLBACK_MONO}


def load_fonts() -> dict[str, str]:
    """Daftarkan Inter & JetBrains Mono dari folder fonts/; pakai Segoe UI/Consolas jika gagal."""
    for path in sorted(FONT_DIR.glob("*.[ot]tf")):
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id < 0:
            continue
        family = QFontDatabase.applicationFontFamilies(font_id)[0]
        if family.startswith("Inter"):
            _families["ui"] = "Inter"
        elif family.startswith("JetBrains Mono"):
            _families["mono"] = "JetBrains Mono"
    return dict(_families)


def ui_family() -> str:
    return _families["ui"]


def mono_family() -> str:
    return _families["mono"]


def font(px: int = 14, weight: QFont.Weight = QFont.Normal, mono: bool = False) -> QFont:
    f = QFont(mono_family() if mono else ui_family())
    f.setPixelSize(max(MIN_FONT_PX, px))
    f.setWeight(weight)
    f.setHintingPreference(QFont.PreferNoHinting)
    return f


def _qss_icon(name: str, color: str) -> str:
    """Tulis ikon SVG untuk dipakai QSS (QSS hanya menerima path file)."""
    from chorale.appdirs import user_config_dir

    folder = user_config_dir() / "ui-cache"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}_{color.strip('#')}.svg"
    if not path.exists():
        path.write_text(icons.svg(name, color), encoding="utf-8")
    return path.as_posix()


def stylesheet() -> str:
    qss = QSS_FILE.read_text(encoding="utf-8")
    tokens = {f"@{k}": v for k, v in COLORS.items()}
    tokens["@font_ui"] = f'"{ui_family()}"'
    tokens["@font_mono"] = f'"{mono_family()}"'
    tokens["@icon_chevron_down"] = _qss_icon("chevron_down", COLORS["text2"])
    tokens["@icon_check"] = _qss_icon("check", "#FFFFFF")
    for key in sorted(tokens, key=len, reverse=True):
        qss = qss.replace(key, tokens[key])
    return qss


def apply(app: QApplication) -> None:
    load_fonts()
    app.setFont(font(14))
    app.setStyleSheet(stylesheet())
