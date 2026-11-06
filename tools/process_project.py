"""Proses proyek menjadi master siap YouTube: WAV + MP3 + laporan (Segmen 4 + 5).

Hasil di folder master/ proyek:
    <Judul>_<YYYYMMDD-HHMM>_Master.wav   (24-bit, 48 kHz, stereo, dither TPDF)
    <Judul>_<YYYYMMDD-HHMM>_Master.mp3   (320 kbps CBR)
    <Judul>_<YYYYMMDD-HHMM>_Laporan.txt
File lama tidak pernah ditimpa.

Cara pakai:
    .venv\\Scripts\\python tools\\process_project.py [--proyek FOLDER] [--ruang katedral] [--reverb normal]
Tanpa --proyek, dipakai proyek yang terakhir dibuka. Ctrl+C membatalkan.
"""

from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools._common import heading, setup_console  # noqa: E402
from chorale.dsp.chain import ProcessingCancelled  # noqa: E402
from chorale.dsp.produce import STEP_LABELS, produce  # noqa: E402
from chorale.dsp.reverb import REVERB_AMOUNT_LABELS, ROOM_PRESETS  # noqa: E402
from chorale.project import list_recent, open_project  # noqa: E402
from chorale.project.model import REVERB_AMOUNT_IDS, ROOM_PRESET_IDS  # noqa: E402


def main() -> int:
    setup_console()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--proyek", type=Path, help="folder proyek (default: proyek terakhir)")
    parser.add_argument("--ruang", choices=ROOM_PRESET_IDS, help="preset ruang (default: dari proyek)")
    parser.add_argument("--reverb", choices=REVERB_AMOUNT_IDS, help="jumlah reverb (default: dari proyek)")
    parser.add_argument("--tanpa-denoise", action="store_true", help="matikan peredam derau semua track")
    parser.add_argument("--tanpa-verifikasi", action="store_true", help="lewati pengukuran ulang dengan FFmpeg")
    args = parser.parse_args()

    if args.proyek is None:
        recent = list_recent()
        if not recent:
            print("Belum ada proyek. Buat contoh: .venv\\Scripts\\python tools\\make_demo_project.py")
            return 1
        args.proyek = Path(recent[0]["path"])
    project = open_project(args.proyek)
    project.autosave = False  # pilihan baris perintah tidak mengubah proyek
    if args.ruang:
        project.room_preset = args.ruang
    if args.reverb:
        project.reverb_amount = args.reverb
    if args.tanpa_denoise:
        for tr in project.tracks.values():
            tr.denoise = False

    heading(f"Memproses Produksi: {project.title}")
    print(f"  Ruang: {ROOM_PRESETS[project.room_preset].label} · {REVERB_AMOUNT_LABELS[project.reverb_amount]}")
    print()

    cancel = threading.Event()
    state: dict = {}
    shown: list[int] = []

    def progress(step: int, percent: float) -> None:
        if not shown or shown[-1] != step:
            shown.append(step)
            print(f"  [{percent:5.1f}%] {step}. {STEP_LABELS[step]}", flush=True)

    def work():
        try:
            state["result"] = produce(project, progress=progress, cancel=cancel,
                                      verify=not args.tanpa_verifikasi)
        except ProcessingCancelled:
            state["cancelled"] = True
        except Exception as exc:  # noqa: BLE001
            state["error"] = exc

    worker = threading.Thread(target=work)
    worker.start()
    try:
        while worker.is_alive():
            worker.join(0.2)
    except KeyboardInterrupt:
        cancel.set()
        worker.join()

    if state.get("cancelled"):
        print("  Dibatalkan.")
        return 1
    if "error" in state:
        print(f"  Gagal: {state['error']}")
        return 1
    result = state["result"]

    heading("Master selesai dibuat")
    print(result.report_path.read_text(encoding="utf-8"))
    print(f"  Folder hasil: {result.wav_path.parent}")
    print()
    return 0 if result.youtube_ready else 2


if __name__ == "__main__":
    sys.exit(main())
