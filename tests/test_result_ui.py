"""Tes UI Proses Produksi & Hasil, termasuk alur penuh lewat jendela utama (Qt offscreen, tanpa sound card)."""

import os
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QPushButton  # noqa: E402

from chorale.audio.ab_player import SOURCE_A, SOURCE_B  # noqa: E402
from chorale.dsp.errors import ProcessingCancelled  # noqa: E402
from chorale.dsp.produce import produce  # noqa: E402
from chorale.project import create_project  # noqa: E402
from chorale.settings import AppSettings, save_settings  # noqa: E402
from chorale.ui.processing import DONE, SKIPPED, eta_text  # noqa: E402
from tools.import_takes import import_demo  # noqa: E402

from tests.test_flow import SELECTION, FakeOutput  # noqa: E402
from tests.test_recording_ui import controller_factory, wait_until  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    from chorale.ui import theme

    app = QApplication.instance() or QApplication([])
    theme.apply(app)
    return app


@pytest.fixture
def fake_audio(monkeypatch):
    from chorale.ui.result_screen import ResultScreen

    monkeypatch.setattr(ResultScreen, "selection_factory", staticmethod(lambda settings: SELECTION))
    monkeypatch.setattr(ResultScreen, "stream_factory", staticmethod(lambda sel, cb, bs: FakeOutput(cb)))
    opened = []
    monkeypatch.setattr(ResultScreen, "open_folder", staticmethod(opened.append))
    return opened


def _project(tmp_path, bars=2):
    p = create_project(tmp_path, "Bapa Engkau Sungguh Baik", count_in_bars=0)
    import_demo(p, bars=bars)
    return p


def texts(widget):
    return {w.text().strip() for w in widget.findChildren(QLabel)} | {
        w.text().strip().replace("&&", "&") for w in widget.findChildren(QPushButton)}


def test_eta_text():
    assert eta_text(0.5, 50) == "Menghitung sisa waktu…"
    assert eta_text(10, 40) == "Sisa sekitar 15 detik"
    assert eta_text(10, 95) == "Sisa kurang dari 10 detik"
    assert eta_text(30, 10) == "Sisa sekitar 4 menit"


def test_processing_overlay_runs_and_finishes(qapp, tmp_path):
    from PySide6.QtWidgets import QWidget

    from chorale.ui.processing import ProcessingOverlay

    host = QWidget()
    host.resize(1440, 900)
    overlay = ProcessingOverlay(host)
    results = []
    overlay.finished.connect(results.append)
    overlay.start(_project(tmp_path))
    assert "Memproses Produksi" in texts(overlay)
    assert overlay.subtitle.text() == "Bapa Engkau Sungguh Baik · Ruang: Katedral"
    for t in ("Membersihkan derau", "Menyaring frekuensi rendah", "Merapikan karakter suara",
              "Menyeimbangkan volume antar-suara", "Menata posisi stereo", "Menambahkan ruang (reverb)",
              "Mastering standar YouTube", "Batalkan"):
        assert t in texts(overlay), t
    assert wait_until(qapp, lambda: results, timeout=60)
    assert not overlay.isVisible()
    assert overlay.icons[1].state == SKIPPED and all(overlay.icons[n].state == DONE for n in range(2, 8))
    assert overlay.percent.text() == "100%"
    assert results[0].wav_path.is_file()


def test_processing_cancel_cleans_up(qapp, tmp_path):
    from PySide6.QtWidgets import QWidget

    from chorale.ui.processing import ProcessingOverlay

    project = _project(tmp_path)
    host = QWidget()
    overlay = ProcessingOverlay(host)
    events = []
    overlay.cancelled.connect(lambda: events.append("batal"))

    def slow_produce(project, progress, cancel, verify):
        return produce(project, progress=lambda s, p: (progress(s, p), time.sleep(0.05)), cancel=cancel,
                       verify=verify)

    overlay.produce_fn = slow_produce
    overlay.start(project)
    assert wait_until(qapp, lambda: overlay.bar.value() > 0, timeout=30)
    overlay.cancel()
    assert overlay.cancel_btn.text() == "Membatalkan…"
    assert wait_until(qapp, lambda: events, timeout=60)
    assert not overlay.isVisible()
    assert list(project.master_dir.iterdir()) == []


def test_processing_failure_shows_error(qapp, tmp_path):
    from PySide6.QtWidgets import QWidget

    from chorale.ui.processing import ProcessingOverlay

    host = QWidget()
    overlay = ProcessingOverlay(host)

    def broken(project, progress, cancel, verify):
        raise RuntimeError("disk penuh")

    overlay.produce_fn = broken
    overlay.start(_project(tmp_path))
    assert wait_until(qapp, lambda: overlay.error.isVisibleTo(overlay), timeout=10)
    assert overlay.error.text() == "Proses gagal: disk penuh"
    assert overlay.cancel_btn.text() == "Tutup"
    overlay.cancel()
    assert not overlay.isVisible()


def test_result_screen(qapp, tmp_path, fake_audio):
    from chorale.ui.result_screen import ResultScreen

    project = _project(tmp_path, bars=3)
    result = produce(project, verify=True)
    screen = ResultScreen()
    screen.resize(1440, 900)
    screen.show()
    screen.show_result(project, result, AppSettings())
    t = texts(screen)
    for expected in ("✓  Master selesai dibuat", "Hasil Produksi", "Pratinjau Master", "24-bit · 48 kHz · Stereo",
                     "Posisi Waktu", "Volume A dan B disamakan agar perbandingan adil.", "Laporan Mastering",
                     "Siap YouTube", "Kelantangan", "Puncak (True Peak)", "Rentang Dinamika (LRA)", "Durasi",
                     "Ruang", "Katedral · Normal", "Ekspor", "3 berkas", "WAV 24-bit · 48 kHz", "MP3 320 kbps",
                     "Laporan", "Buka Folder Hasil", "Kembali & Ubah Pengaturan", "Proses Ulang"):
        assert expected in t, expected
    assert screen.rows["lufs"].value.text().endswith(" LUFS") and screen.rows["tp"].value.text().endswith(" dBTP")
    assert screen.files[0].name.text().endswith("_Master.wav") and "..." in screen.files[0].name.text()
    assert screen.ab.button(SOURCE_B).text().startswith("✓") and screen.ab.button(SOURCE_A).text().startswith("○")

    screen.toggle_play()
    assert wait_until(qapp, lambda: screen.player.position_seconds > 0.2)
    pos = screen.player.position_seconds
    screen.ab.button(SOURCE_A).click()
    assert screen.player.source == SOURCE_A and screen.player.position_seconds >= pos
    assert screen.ab.button(SOURCE_A).text().startswith("✓")
    screen.toggle_play()
    assert not screen.player.playing

    screen.open_btn.click()
    assert fake_audio == [result.wav_path]
    back = []
    screen.backRequested.connect(lambda: back.append(1))
    redo = []
    screen.reprocessRequested.connect(redo.append)
    [b for b in screen.findChildren(QPushButton) if "Proses Ulang" in b.text()][0].click()
    assert redo == [project]
    [b for b in screen.findChildren(QPushButton) if "Kembali & Ubah" in b.text().replace("&&", "&")][0].click()
    assert back == [1] and screen.player is None


def test_full_flow_through_main_window(qapp, tmp_path, fake_audio, monkeypatch):
    """Daftar Proyek -> Proyek Baru -> (5 take diimpor) -> Proses -> Hasil -> Buka Folder -> Kembali."""
    from chorale.ui.main_window import MainWindow
    from chorale.ui.recording_screen import RecordingScreen

    monkeypatch.setattr(RecordingScreen, "controller_factory", controller_factory())
    save_settings(AppSettings(projects_dir=str(tmp_path)))
    w = MainWindow()
    w.show()
    w.show_new_project()
    w.new_project.title_edit.setText("Malam Kudus")
    w.new_project.count_in.set_value(0)
    folder = w.new_project.submit()
    assert w.stack.currentWidget() is w.recording
    assert not w.recording.produce_btn.isEnabled()

    import_demo(w.recording.project, bars=2)  # pengganti merekam 5 track
    w.recording.refresh_tracks()
    assert w.recording.produce_btn.isEnabled()
    w.recording.produce_btn.click()
    assert w.processing.isVisible() and w.recording.controller is not None
    assert wait_until(qapp, lambda: w.stack.currentWidget() is w.result_screen, timeout=90)
    assert w.result_screen.ready_badge.text() == "Siap YouTube"
    w.result_screen.open_btn.click()
    assert fake_audio and fake_audio[-1].parent == folder / "master"
    assert len(list((folder / "master").iterdir())) == 3

    w.result_screen._back()
    assert w.stack.currentWidget() is w.recording
    assert w.recording.room.value() == "katedral", "pengaturan tetap"
    w.recording.shutdown()
    w.result_screen.shutdown()


def test_reprocess_and_cancel_returns_to_result(qapp, tmp_path, fake_audio, monkeypatch):
    from chorale.ui.main_window import MainWindow
    from chorale.ui.recording_screen import RecordingScreen

    monkeypatch.setattr(RecordingScreen, "controller_factory", controller_factory())
    project = _project(tmp_path)
    save_settings(AppSettings(projects_dir=str(tmp_path)))
    w = MainWindow()
    w.show()
    w.open_folder(project.folder)
    w.recording.produce_btn.click()
    assert wait_until(qapp, lambda: w.stack.currentWidget() is w.result_screen, timeout=90)
    first = w.result_screen.result.wav_path

    def slow(project, progress, cancel, verify):
        def tick(s, p):
            progress(s, p)
            time.sleep(0.05)
        return produce(project, progress=tick, cancel=cancel, verify=verify)

    w.processing.produce_fn = slow
    w.result_screen._reprocess()
    assert wait_until(qapp, lambda: w.processing.bar.value() > 0, timeout=30)
    w.processing.cancel()
    assert wait_until(qapp, lambda: not w.processing.isVisible(), timeout=60)
    assert w.stack.currentWidget() is w.result_screen and w.result_screen.player is not None
    assert "dibatalkan" in w.result_screen.toast.text()
    assert sorted(p.name for p in project.master_dir.iterdir()) == sorted(
        [first.name, first.name.replace("_Master.wav", "_Master.mp3"), first.name.replace("_Master.wav", "_Laporan.txt")])
    w.result_screen.shutdown()
    w.recording.shutdown()


__all__ = ["ProcessingCancelled", "threading", "np"]
