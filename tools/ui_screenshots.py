r"""Ambil screenshot tiap layar untuk dibandingkan dengan mockup design/.

Data contoh (4 proyek seperti mockup) dibuat di folder sementara; %APPDATA%
juga diarahkan ke folder sementara, jadi pengaturan & proyek asli tidak tersentuh.
Meter input memakai sound card yang benar-benar tersambung.

Cara pakai:
    .venv\Scripts\python tools\ui_screenshots.py [--out docs\screenshots]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="harmonisatb_ui_"))
os.environ["APPDATA"] = str(TMP / "appdata")
sys.path.insert(0, str(ROOT / "src"))

from chorale.audio import device  # noqa: E402,F401
from chorale.project import Take, add_recent, create_project  # noqa: E402

SAMPLES = [  # judul, tempo, birama, track terekam, waktu diubah (seperti mockup)
    ("Haleluya Puji Tuhan", 96, "3/4", 0, "2026-10-28T18:30:00"),
    ("Malam Kudus", 60, "6/8", 1, "2026-11-02T20:12:00"),
    ("Kudus, Kudus, Kudus", 66, "4/4", 3, "2026-11-05T19:40:00"),
    ("Bapa Engkau Sungguh Baik", 72, "4/4", 5, "2026-11-06T13:05:00"),
]


def make_samples() -> Path:
    folder = TMP / "Documents" / "HarmoniSATB"
    folder.mkdir(parents=True)
    for title, tempo, ts, recorded, modified in SAMPLES:
        p = create_project(folder, title, tempo=tempo, time_signature=ts)
        p.autosave = False
        for tid in list(p.tracks)[:recorded]:
            p.tracks[tid].takes.append(Take(1, f"{tid}_take1_20261101-100000.wav", modified, 60.0))
            p.tracks[tid].active_take_id = 1
        data = p.to_dict()
        data["modified_at"] = modified
        p.project_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        add_recent(p)
    return folder


def wait(app, ms: int) -> None:
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "screenshots")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    from PySide6.QtWidgets import QApplication

    from chorale.settings import AppSettings, save_settings
    from chorale.ui import theme
    from chorale.ui.main_window import MainWindow

    projects_dir = make_samples()
    save_settings(AppSettings(projects_dir=str(projects_dir)))
    app = QApplication([])
    theme.apply(app)
    w = MainWindow()
    w.resize(1440, 900)
    w.show()
    wait(app, 400)

    def shot(name: str) -> None:
        wait(app, 150)
        path = args.out / f"{name}.png"
        w.grab().save(str(path))
        print(f"  {path.relative_to(ROOT)}")

    shot("01_daftar_proyek")
    w.show_new_project()
    shot("02_proyek_baru")
    w.new_project.submit()
    shot("03_proyek_baru_validasi")
    w.new_project.close_overlay()
    w.show_settings()
    wait(app, 900)  # beri waktu meter input menampilkan level
    shot("04_pengaturan_perangkat_audio")
    w.settings_screen.nav_about.click()
    shot("05_pengaturan_tentang")
    w.settings_screen.cancel()
    w.resize(1280, 800)
    w.show_projects()
    shot("06_daftar_proyek_1280x800")
    w.show_settings()
    wait(app, 300)
    shot("07_pengaturan_1280x800")
    w.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
