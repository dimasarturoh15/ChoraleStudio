"""Tes antarmuka (Qt offscreen, tanpa sound card) dan logika pendukungnya."""

import json
import os
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from chorale.audio import calibration as cal  # noqa: E402
from chorale.audio.device import (  # noqa: E402
    MODE_ASIO, MODE_EXCLUSIVE, MODE_SHARED, AudioDeviceError, DeviceInfo, DeviceSelection, SoundCard, card_name,
    list_sound_cards, select_device,
)
from chorale.project import Take, add_recent, create_project, open_project  # noqa: E402
from chorale.project.store import read_summary  # noqa: E402
from chorale.settings import AppSettings, load_settings, save_settings, settings_path  # noqa: E402

W = "Windows WASAPI"


@pytest.fixture(scope="module")
def qapp():
    from chorale.ui import theme

    app = QApplication.instance() or QApplication([])
    theme.apply(app)
    return app


# ----- logika non-UI -----

def _dev(i, name, api=W, i_ch=0, o_ch=0):
    return DeviceInfo(i, name, api, i_ch, o_ch, 48000.0)


FAKE_DEVICES = [
    _dev(0, "Microphone (Realtek(R) Audio)", i_ch=2),
    _dev(1, "Speakers (Realtek(R) Audio)", o_ch=2),
    _dev(2, "Line (SPL Audio SC202HD)", i_ch=2),
    _dev(3, "Speakers (SPL Audio SC202HD)", o_ch=2),
    _dev(4, "SPL ASIO Driver", "ASIO", 2, 2),
    _dev(5, "Speakers (FxSound Audio Enhancer)", o_ch=2),
    _dev(6, "SPL Audio SC202HD", "MME", 2, 0),
]


def test_card_name():
    assert card_name("Microphone (Realtek(R) Audio)") == "Realtek(R) Audio"
    assert card_name("SPL ASIO Driver") == "SPL ASIO Driver"


def test_list_sound_cards_groups_and_orders():
    cards = list_sound_cards(FAKE_DEVICES)
    names = [c.name for c in cards]
    assert names[0] in ("SPL Audio SC202HD", "SPL ASIO Driver")
    assert "Realtek(R) Audio" in names
    assert "FxSound Audio Enhancer" not in names, "kartu tanpa input tidak ditampilkan"
    spl = next(c for c in cards if c.name == "SPL Audio SC202HD")
    assert spl.modes == (MODE_EXCLUSIVE, MODE_SHARED)
    asio = next(c for c in cards if c.name == "SPL ASIO Driver")
    assert asio.modes == (MODE_ASIO,)


def test_select_device_with_forced_mode():
    s = select_device("SC202", FAKE_DEVICES, accepts=lambda sel: True, mode=MODE_SHARED)
    assert s.mode == MODE_SHARED and s.input.index == 2 and s.output.index == 3
    with pytest.raises(AudioDeviceError, match="ASIO"):
        select_device("Realtek", FAKE_DEVICES, accepts=lambda sel: True, mode=MODE_ASIO)


def test_settings_roundtrip_and_validation():
    s = AppSettings(device_name="SPL Audio SC202HD", driver_mode=MODE_SHARED, blocksize=512,
                    instrument_input="1", vocal_input="2")
    save_settings(s)
    assert load_settings() == s
    assert s.instrument_channels() == (0, 1) and s.vocal_channel() == 1
    assert AppSettings().instrument_channels() == (0, 2)
    settings_path().write_text(json.dumps({"blocksize": 999, "driver_mode": "aneh", "lain": 1}), encoding="utf-8")
    loaded = load_settings()
    assert loaded.blocksize == 256 and loaded.driver_mode is None


def test_read_summary_does_not_modify_project(tmp_path):
    p = create_project(tmp_path, "Malam Kudus", tempo=60, time_signature="6/8")
    p.add_take("piano", Take(1, "piano_take1_20261102-201200.wav", "2026-11-02T20:12:00", 1.0))
    before = p.project_file.read_bytes()
    s = read_summary(p.folder)
    assert (s.title, s.tempo, s.time_signature) == ("Malam Kudus", 60, "6/8")
    assert s.recorded == (True, False, False, False, False)
    assert p.project_file.read_bytes() == before
    assert read_summary(tmp_path / "tidak-ada") is None


def test_measure_latency_with_fake_loopback(monkeypatch):
    """Logika kalibrasi yang dipindah dari tools/ bekerja lewat stream palsu ber-latensi 700 sampel."""
    import sounddevice as sd

    class LoopStream:
        def __init__(self, callback, lag):
            self.cb, self.lag, self.latency, self.active = callback, lag, (0.005, 0.005), False
            self.history = np.zeros(200_000, np.float32)

        def start(self):
            self.active = True
            threading.Thread(target=self._run).start()

        def _run(self):
            t = 0
            try:
                while True:
                    ind = np.zeros((256, 2), np.float32)
                    src = t - self.lag
                    if src + 256 > 0:
                        a = max(0, -src)
                        ind[a:, 0] = 0.4 * self.history[src + a:src + 256]
                    out = np.zeros((256, 2), np.float32)
                    self.cb(ind, out, 256, None, None)
                    self.history[t:t + 256] = out[:, 0]
                    t += 256
            except sd.CallbackStop:
                pass
            self.active = False

        def close(self):
            pass

    lags = iter([700, 700, 701, 700, 700])
    monkeypatch.setattr("chorale.audio.device.open_duplex_stream",
                        lambda sel, cb, bs: LoopStream(cb, next(lags)))
    sel = DeviceSelection(W, _dev(0, "In", i_ch=2), _dev(1, "Out", o_ch=2), True)
    seen = []
    result = cal.measure_latency(sel, 256, runs=5, progress=lambda r, n, lag: seen.append(lag))
    assert result.latency_samples == 700 and result.spread_samples == 1
    assert seen == [700, 700, 701, 700, 700]
    assert cal.accuracy_label(result) == ("Akurat", "baik")


# ----- UI -----

def test_theme_fonts_and_minimum_size(qapp):
    from chorale.ui import theme

    families = theme.load_fonts()
    assert families == {"ui": "Inter", "mono": "JetBrains Mono"}
    assert theme.font(9).pixelSize() == 13
    import re

    qss = re.sub(r"/\*.*?\*/", "", theme.stylesheet(), flags=re.S)
    assert not re.search(r"@[a-z_]+", qss), "semua token harus terganti"
    assert "#0E1116" in qss and '"Inter"' in qss and '"JetBrains Mono"' in qss


def test_project_list_shows_recent_projects(qapp, tmp_path):
    from chorale.ui.project_list import ProjectListScreen, format_date

    for title, recorded in (("Haleluya Puji Tuhan", 0), ("Bapa Engkau Sungguh Baik", 5)):
        p = create_project(tmp_path, title)
        for tid in list(p.tracks)[:recorded]:
            p.add_take(tid, Take(1, f"{tid}_take1_20261106-130500.wav", "2026-11-06T13:05:00", 1.0))
        add_recent(p)
    screen = ProjectListScreen()
    assert screen.row_count() == 2
    first = screen._rows.itemAt(0).widget()
    assert first.summary.title == "Bapa Engkau Sungguh Baik"
    assert first.summary.recorded == (True,) * 5
    assert format_date("2026-11-06T13:05:44") == "06-11-2026 13:05"
    assert not screen._empty.isVisibleTo(screen)


def test_project_list_empty_state(qapp):
    from chorale.ui.project_list import ProjectListScreen

    screen = ProjectListScreen()
    assert screen.row_count() == 0 and screen._empty.isVisibleTo(screen)


def test_new_project_validation_and_creation(qapp, tmp_path):
    from PySide6.QtWidgets import QWidget

    from chorale.ui.new_project import MSG_EMPTY_TITLE, NewProjectOverlay

    host = QWidget()
    host.resize(1440, 900)
    overlay = NewProjectOverlay(tmp_path / "Proyek", host)
    overlay.open()
    created = []
    overlay.created.connect(created.append)

    assert overlay.submit() is None
    assert overlay.error.text() == MSG_EMPTY_TITLE and overlay.error.isVisibleTo(overlay)
    assert not (tmp_path / "Proyek").exists()

    overlay.title_edit.setText("Kudus, Kudus, Kudus")
    assert not overlay.error.isVisibleTo(overlay)
    overlay.tempo.edit.setText("300")
    assert overlay.tempo.value() == 240
    overlay.tempo.edit.setText("12")
    assert overlay.tempo.value() == 40
    overlay.tempo.set_value(66)
    overlay.tempo.step(+1)
    overlay.time_signature.set_value("3/4")
    overlay.count_in.set_value(1)
    overlay.metronome.setChecked(False)
    folder = overlay.submit()

    assert created == [folder] and folder.parent == tmp_path / "Proyek"
    p = open_project(folder)
    assert (p.title, p.tempo, p.time_signature, p.count_in_bars, p.metronome_after_count_in) == (
        "Kudus, Kudus, Kudus", 67, "3/4", 1, False)


def test_new_project_texts_match_mockup(qapp, tmp_path):
    from PySide6.QtWidgets import QLabel, QPushButton, QWidget

    from chorale.ui.new_project import NewProjectOverlay

    host = QWidget()
    overlay = NewProjectOverlay(tmp_path, host)
    texts = {w.text().strip() for w in overlay.findChildren(QLabel)} | {
        w.text().strip() for w in overlay.findChildren(QPushButton)}
    for expected in ("Proyek Baru", "Judul Lagu", "Tempo (BPM)", "Birama", "40 – 240", "Hitungan Awal",
                     "Metronom tetap bunyi setelah hitungan awal", "Matikan untuk lagu bertempo bebas.",
                     "Batal", "Buat Proyek"):
        assert expected in texts, expected
    assert overlay.title_edit.placeholderText() == "Contoh: Bapa Engkau Sungguh Baik"


def test_settings_page_with_fake_card(qapp, monkeypatch):
    from chorale.ui.settings_screen import SettingsScreen

    monkeypatch.setattr("chorale.audio.device.select_device",
                        lambda name, mode=None: DeviceSelection(
                            W, _dev(0, f"Line ({name})", i_ch=2), _dev(1, f"Speakers ({name})", o_ch=2),
                            mode == MODE_EXCLUSIVE))
    screen = SettingsScreen()
    cards = [SoundCard("SPL Audio SC202HD", (MODE_EXCLUSIVE, MODE_SHARED), 2, 2)]
    screen.open(AppSettings(blocksize=512), cards)
    page = screen.audio_page
    asio = page.mode.button(MODE_ASIO)
    assert not asio.isEnabled() and asio.sublabel == "Tidak tersedia"
    assert page.mode.value() == MODE_EXCLUSIVE
    assert page.buffer_combo.currentText() == "512 sampel"
    assert page.latency_value.text() == "—" and page.accuracy_badge.text() == "Belum dikalibrasi"

    page.mode.button(MODE_SHARED).click()
    page.vocal_combo.setCurrentIndex(1)
    saved = []
    screen.saved.connect(saved.append)
    screen.save()
    assert saved[0].driver_mode == MODE_SHARED and saved[0].vocal_input == "2"
    assert load_settings().device_name == "SPL Audio SC202HD"


def test_settings_shows_saved_calibration(qapp, monkeypatch):
    from chorale.ui.settings_screen import SettingsScreen

    monkeypatch.setattr("chorale.audio.device.select_device",
                        lambda name, mode=None: DeviceSelection(
                            W, _dev(0, "Line (X)", i_ch=2), _dev(1, "Speakers (X)", o_ch=2), True))
    cal.save_calibration(cal.CalibrationResult(
        input_device="Line (X)", output_device="Speakers (X)", hostapi=W, exclusive=True, samplerate=48000,
        blocksize=256, latency_samples=595, latency_ms=12.396, runs_samples=[595] * 5, spread_samples=0,
        date="2026-11-06T13:15:00"))
    screen = SettingsScreen()
    screen.open(AppSettings(), [SoundCard("X", (MODE_EXCLUSIVE, MODE_SHARED), 2, 2)])
    page = screen.audio_page
    assert page.latency_value.text() == "12.4 ms"
    assert page.accuracy_badge.text() == "✓ Akurat"
    assert page.last_calibrated.text() == "Terakhir dikalibrasi 06-11-2026 13:15"


def test_main_window_navigation(qapp, tmp_path, monkeypatch):
    from chorale.ui.main_window import MainWindow

    # Tanpa sound card: layar perekaman tidak boleh membuka perangkat sungguhan di tes.
    monkeypatch.setattr("chorale.ui.audio_controller.AudioController.connect_device",
                        lambda self, refresh=False: False)
    save_settings(AppSettings(projects_dir=str(tmp_path)))
    w = MainWindow()
    assert (w.width(), w.height()) == (1440, 900)
    assert (w.minimumWidth(), w.minimumHeight()) == (1280, 800)
    assert w.stack.currentWidget() is w.projects
    w.show_settings()
    assert w.stack.currentWidget() is w.settings_screen
    w.settings_screen.cancel()
    assert w.stack.currentWidget() is w.projects
    w.show_new_project()
    w.new_project.title_edit.setText("Lagu Baru")
    folder = w.new_project.submit()
    assert w.stack.currentWidget() is w.recording
    assert w.recording.title.text() == "Lagu Baru" and folder.parent == tmp_path
    w.show_projects()
    assert w.projects.row_count() == 1
    w.recording.shutdown()
    w.settings_screen.shutdown()
