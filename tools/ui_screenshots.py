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
sys.path.insert(0, str(ROOT))

from chorale.audio import device  # noqa: E402,F401
from chorale.audio.session import WARMUP_SECONDS  # noqa: E402
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
        w.recording.toast.hide()
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
    w.settings_screen.cancel()
    w.resize(1440, 900)
    recording_shots(app, w, shot, projects_dir)
    w.close()
    return 0


class SimStream:
    """Stream SIMULASI (tanpa sound card): callback dipanggil dari thread dengan nada 220 Hz."""

    def __init__(self, callback, die_after=None):
        import threading

        import numpy as np

        self.callback, self.die_after = callback, die_after
        self.latency, self.cpu_load = (0.006, 0.006), 0.05
        t = np.arange(256) / 48000
        self.block = np.repeat((0.28 * np.sin(2 * np.pi * 220 * t))[:, None], 2, axis=1).astype(np.float32)
        self._halt = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        import numpy as np

        n = 0
        while not self._halt.is_set() and (self.die_after is None or n < self.die_after):
            env = 0.6 + 0.4 * np.sin(n / 40)
            self.callback(self.block * np.float32(env), np.empty((256, 2), np.float32), 256, None, None)
            n += 1
            time.sleep(256 / 48000)

    def start(self):
        self._thread.start()

    def stop(self):
        self._halt.set()
        self._thread.join(2)

    def close(self):
        pass


def recording_shots(app, w, shot, projects_dir: Path) -> None:
    """Layar perekaman: diam, daftar take, merekam, wizard vokal, sound card terputus, 1280x800."""
    import shutil

    from PySide6.QtGui import QPainter

    from chorale.audio.device import DeviceInfo, DeviceSelection
    from chorale.audio.meter import LevelMeter
    from chorale.project import Take, open_project
    from chorale.ui.audio_controller import AudioController
    from tools.make_demo_project import create_demo

    selection = DeviceSelection(
        "Windows WASAPI",
        DeviceInfo(0, "Line (SPL Audio SC202HD)", "Windows WASAPI", 2, 0, 48000.0),
        DeviceInfo(1, "Speakers (SPL Audio SC202HD)", "Windows WASAPI", 0, 2, 48000.0), True)

    class SimMonitor:
        def __init__(self, sel, blocksize):
            self.meter, self.active = LevelMeter(2), True

        def start(self):
            pass

        def stop(self):
            self.active = False

    die_after = {"n": None}

    class SimController(AudioController):
        def __init__(self, project, settings):
            super().__init__(project, settings, monitor_factory=SimMonitor,
                             stream_factory=lambda sel, cb, bs, finished_callback=None: SimStream(cb, die_after["n"]))

        def connect_device(self, refresh=False):
            self.selection, self.device_error = selection, None
            return True

        def latency_ms(self):
            return 12.4, True

    w.recording.controller_factory = SimController
    demo = create_demo(projects_dir, "Bapa Engkau Sungguh Baik", bars=24)
    demo.autosave = False
    # Bass punya 3 take (take 3 tidak lengkap); Alto & Sopran belum direkam.
    bass_take = demo.tracks["bass"].active_take
    for n, (stamp, complete) in enumerate((("20261106-130100", True), ("20261106-130600", False)), start=2):
        name = f"bass_take{n}_{stamp}.wav"
        shutil.copyfile(demo.take_path(bass_take), demo.takes_dir / name)
        demo.tracks["bass"].takes.append(Take(n, name, f"2026-11-06T{stamp[9:11]}:{stamp[11:13]}:00",
                                              bass_take.duration if complete else 72.0, complete))
    demo.tracks["bass"].active_take_id = 2
    for tid in ("alto", "sopran"):
        for take in demo.tracks[tid].takes:  # file contoh dihapus agar tidak dipulihkan sebagai take yatim
            demo.take_path(take).unlink()
        demo.tracks[tid].takes.clear()
        demo.tracks[tid].active_take_id = None
    demo.vocal_guide_done = True
    demo.save()
    w.open_folder(demo.folder)
    wait(app, 1500)  # waveform dihitung di latar
    shot("08_layar_rekam")

    w.recording._open_takes("bass")
    wait(app, 200)
    panel = w.recording._take_panel
    image = w.grab()
    painter = QPainter(image)
    painter.drawPixmap(w.mapFromGlobal(panel.pos()), panel.grab())
    painter.end()
    out = ROOT / "docs" / "screenshots" / "09_pilih_take.png"
    image.save(str(out))
    print(f"  {out.relative_to(ROOT)}")
    panel.close()

    def wait_for(cond, timeout=60.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end and not cond():
            app.processEvents()
            time.sleep(0.01)
        if not cond():
            raise RuntimeError("Kondisi tidak tercapai saat membuat screenshot")

    ctrl = lambda: w.recording.controller  # noqa: E731

    def record_skipping_gain_check(track_id: str) -> None:
        """Rekam tanpa berhenti di panduan cek gain (muncul untuk kelompok suara yang belum punya take)."""
        w.recording.record(track_id)
        if w.recording.guide.isVisible():
            while w.recording.guide.isVisible():
                w.recording.guide.next()
                app.processEvents()

    record_skipping_gain_check("alto")
    wait_for(lambda: ctrl().mode == "recording" and ctrl().session.song_seconds > -1.7)
    shot("10_merekam")
    w.recording.stop()
    wait_for(lambda: ctrl().mode == "idle")

    project = open_project(demo.folder)
    project.vocal_guide_done = False
    w.recording.project.vocal_guide_done = False
    for tid in ("bass", "tenor", "alto"):
        w.recording.project.tracks[tid].takes.clear()
        w.recording.project.tracks[tid].active_take_id = None
    w.recording.refresh_tracks()
    w.recording.record("bass")
    w.recording.guide.next()
    w.recording.timer.stop()  # level wizard diisi manual (-11,8 dBFS) untuk screenshot
    w.recording.guide.update_level(-11.8)
    shot("11_persiapan_rekam_vokal")
    w.recording.guide.close_overlay()
    w.recording.timer.start()

    w.recording.project.vocal_guide_done = True
    # Pemanasan 5 s + hitungan awal 3,3 s, lalu "dicabut" sekitar 3 s setelah rekaman dimulai.
    die_after["n"] = 1250 + int(WARMUP_SECONDS * 48000 / 256)
    record_skipping_gain_check("alto")
    wait_for(lambda: w.recording.error_overlay.isVisible() and ctrl().mode == "idle")
    shot("12_sound_card_terputus")
    w.recording.error_overlay.close_overlay()
    die_after["n"] = None
    w.recording.controller.connect_device()

    w.resize(1280, 800)
    wait(app, 300)
    shot("13_layar_rekam_1280x800")
    w.resize(1440, 900)
    production_shots(app, w, shot, demo.folder, selection)
    w.recording.shutdown()


def production_shots(app, w, shot, folder: Path, selection) -> None:
    """Dialog Memproses Produksi (di tengah jalan) dan layar Hasil Produksi."""
    from chorale.dsp.produce import produce
    from chorale.project import open_project
    from chorale.ui.result_screen import ResultScreen

    # Isi kelima track dengan suara SATB sintetis (pengganti merekam; lihat tools/import_takes.py).
    from tools.import_takes import import_demo

    project = w.recording.project
    import_demo(project, bars=24)
    w.recording.refresh_tracks()
    w.recording._update_pill()
    wait(app, 300)

    ResultScreen.selection_factory = staticmethod(lambda settings: selection)
    ResultScreen.stream_factory = staticmethod(lambda sel, cb, bs: SimOutput(cb))
    ResultScreen.open_folder = staticmethod(lambda path: print(f"  (Buka Folder Hasil -> {path.name})"))

    def slow_produce(project, progress, cancel, verify):
        def tick(step, pct):
            progress(step, pct)
            if 54 <= pct <= 60:
                time.sleep(0.6)
        return produce(project, progress=tick, cancel=cancel, verify=verify)

    w.processing.produce_fn = slow_produce
    if not w.recording.produce_btn.isEnabled():
        raise RuntimeError("Tombol Proses Produksi & Master belum aktif")
    w.recording.produce_btn.click()
    end = time.monotonic() + 120
    while time.monotonic() < end and w.processing.bar.value() < 540:
        app.processEvents()
        time.sleep(0.01)
    shot("14_memproses_produksi")
    end = time.monotonic() + 180
    while time.monotonic() < end and w.stack.currentWidget() is not w.result_screen:
        app.processEvents()
        time.sleep(0.02)
    if w.stack.currentWidget() is not w.result_screen:
        raise RuntimeError(f"Layar hasil tidak muncul: {w.processing.error.text()!r}")
    w.result_screen.player.seek(w.result_screen.player.length_seconds * 0.19)
    wait(app, 200)
    shot("15_hasil_produksi")
    w.result_screen.toggle_play()
    wait(app, 600)
    w.result_screen.ab.button(0).click()
    wait(app, 300)
    shot("16_hasil_ab_mentah")
    w.result_screen.toggle_play()
    w.result_screen.open_btn.click()
    w.resize(1280, 800)
    wait(app, 300)
    shot("17_hasil_produksi_1280x800")
    w.result_screen.shutdown()


class SimOutput:
    """Output SIMULASI untuk pemutar A/B (tanpa suara keluar)."""

    def __init__(self, callback):
        import threading

        self.callback, self._halt = callback, threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        import numpy as np

        while not self._halt.is_set():
            self.callback(np.empty((256, 2), np.float32), 256, None, None)
            time.sleep(256 / 48000)

    def start(self):
        self._thread.start()

    def stop(self):
        self._halt.set()
        self._thread.join(2)

    def close(self):
        pass


if __name__ == "__main__":
    sys.exit(main())
