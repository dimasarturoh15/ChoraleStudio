"""Tes layar perekaman (Qt offscreen) dengan stream & monitor palsu — tanpa sound card."""

import os
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402
import soundfile as sf  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QPushButton  # noqa: E402

from chorale.audio.device import DeviceInfo, DeviceSelection  # noqa: E402
from chorale.audio.meter import LevelMeter  # noqa: E402
from chorale.project import TRACK_IDS, Take, create_project  # noqa: E402
from chorale.settings import AppSettings  # noqa: E402
from chorale.ui.audio_controller import IDLE, PLAYING, RECORDING, AudioController  # noqa: E402
from chorale.ui.vocal_guide import level_status  # noqa: E402
from chorale.ui.waveform import PEAK_RATE, compute_peaks, peak_at, view_seconds_for  # noqa: E402

SR = 48000
BLOCK = 256
SELECTION = DeviceSelection(
    "Windows WASAPI",
    DeviceInfo(0, "Line (SPL Audio SC202HD)", "Windows WASAPI", 2, 0, 48000.0),
    DeviceInfo(1, "Speakers (SPL Audio SC202HD)", "Windows WASAPI", 0, 2, 48000.0),
    exclusive=True,
)


@pytest.fixture(scope="module")
def qapp():
    from chorale.ui import theme

    app = QApplication.instance() or QApplication([])
    theme.apply(app)
    return app


class FakeStream:
    """Memanggil callback terus-menerus (±10x lebih cepat dari waktu nyata) sampai stop()."""

    def __init__(self, callback, die_after=None, level=0.3):
        self.callback, self.die_after = callback, die_after
        self.latency, self.cpu_load = (0.005, 0.005), 0.05
        t = np.arange(BLOCK) / SR
        self.block = np.repeat((level * np.sin(2 * np.pi * 440 * t))[:, None], 2, axis=1).astype(np.float32)
        self._halt = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        n = 0
        while not self._halt.is_set():
            if self.die_after is not None and n >= self.die_after:
                return  # perangkat "dicabut": callback berhenti tanpa pemberitahuan
            out = np.empty((BLOCK, 2), dtype=np.float32)
            self.callback(self.block, out, BLOCK, None, None)
            n += 1
            time.sleep(0.0005)

    def start(self):
        self._thread.start()

    def stop(self):
        self._halt.set()
        self._thread.join(2)

    def close(self):
        pass


class FakeMonitor:
    def __init__(self, selection, blocksize):
        self.meter = LevelMeter(2)
        self.active = True

    def start(self):
        self.meter.update(np.full((4, 2), 0.25, dtype=np.float32))

    def stop(self):
        self.active = False


def controller_factory(die_after=None, connect_ok=True):
    class FakeController(AudioController):
        warmup_seconds = 0.0  # stream palsu pendek; pemanasan diuji di test_warmup_loopback.py

        def __init__(self, project, settings):
            super().__init__(project, settings,
                             stream_factory=lambda sel, cb, bs, finished_callback=None: FakeStream(cb, die_after),
                             monitor_factory=FakeMonitor)

        def connect_device(self, refresh=False):
            if connect_ok:
                self.selection, self.device_error = SELECTION, None
                return True
            self.selection, self.device_error = None, "Sound card tidak ditemukan."
            return False

    return FakeController


def wait_until(app, cond, timeout=8.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    return False


def _project(tmp_path, takes=(), **kw):
    settings = dict(count_in_bars=0, metronome_after_count_in=False)
    settings.update(kw)
    p = create_project(tmp_path, "Bapa Engkau Sungguh Baik", **settings)
    for tid, n, complete in takes:
        number, path = p.next_take_path(tid)
        ch = 2 if tid == "piano" else 1
        sf.write(str(path), 0.2 * np.ones((SR * n, ch), np.float32), SR, subtype="PCM_24")
        p.add_take(tid, Take(number, path.name, "2026-11-06T13:01:00", float(n), complete))
    return p


def _screen(qapp, project, factory=None):
    from chorale.ui.recording_screen import RecordingScreen

    screen = RecordingScreen()
    screen.controller_factory = factory or controller_factory()
    screen.resize(1440, 900)
    screen.show()
    screen.show_project(project, AppSettings())
    qapp.processEvents()
    return screen


# ----- waveform & util -----

def test_compute_peaks_and_lookup(tmp_path):
    path = tmp_path / "a.wav"
    x = np.zeros((SR * 2, 1), np.float32)
    x[SR:SR + 480] = 0.5
    sf.write(str(path), x, SR, subtype="PCM_24")
    peaks = compute_peaks(path)
    assert len(peaks) == 2 * PEAK_RATE
    assert peaks[PEAK_RATE] == pytest.approx(0.5, abs=1e-4) and peaks[:PEAK_RATE].max() == 0
    assert peak_at(peaks, 1.01) == pytest.approx(0.5, abs=1e-4)
    assert peak_at(peaks, 0.5) == 0 and peak_at(None, 1.0) == 0
    assert view_seconds_for([12.0]) == 31 and view_seconds_for([100.0], 120.0) == 123


def test_waveform_view_columns_and_live(qapp):
    from chorale.ui.waveform import WaveformView

    w = WaveformView("#14B8A6")
    w.resize(600, 100)
    w.set_view_seconds(10)
    w.set_peaks(np.full(5 * PEAK_RATE, 0.5, np.float32))
    cols = w._compute_columns(576)
    assert cols[:280].min() > 0.8 and cols[300:].max() == 0  # 5 dari 10 detik terisi
    w.start_live()
    w.append_live(2.0, 0.25)
    assert w._live_len == 2 * PEAK_RATE and w.has_audio()


@pytest.mark.parametrize("db,level", [(-60, "kosong"), (-20, "pelan"), (-11.8, "pas"), (-6, "keras"), (-1, "keras")])
def test_level_status(db, level):
    assert level_status(db)[1] == level
    assert level_status(-12)[0] == "Level sudah pas"


def test_clock_and_input_text():
    from chorale.ui.recording_screen import fmt_clock, input_text

    assert fmt_clock(84.36) == "01:24.360" and fmt_clock(-2.5) == "-00:02.500"
    assert input_text("piano", AppSettings()) == "Input 1–2 · Stereo"
    assert input_text("alto", AppSettings(vocal_input="2")) == "Input 2 · Mic"


# ----- layar -----

def test_layout_texts_and_control_width(qapp, tmp_path):
    from chorale.ui.track_strip import CONTROL_WIDTH

    screen = _screen(qapp, _project(tmp_path))
    texts = {w.text() for w in screen.findChildren(QLabel)} | {
        w.text().strip().replace("&&", "&") for w in screen.findChildren(QPushButton)}
    for t in ("Tempo", "Birama", "Hitungan Awal", "Volume Metronom", "Metronom", "Ruang", "Jumlah Reverb",
              "Gereja Kecil", "Aula", "Katedral", "Proses Produksi & Master", "Rekam kelima track terlebih dahulu",
              "Piano/Orgen", "Bass", "Tenor", "Alto", "Sopran", "Input 1–2 · Stereo", "Input 1 · Mic", "Pengaturan"):
        assert t in texts or t in {b.text() for b in screen.room._buttons.values()}, t
    for strip in screen.strips.values():
        assert strip.findChild(QLabel).parent().width() <= CONTROL_WIDTH
        name, inp = strip.name, strip.input_label
        assert name.fontMetrics().horizontalAdvance(name.text()) <= name.width()
        assert inp.fontMetrics().horizontalAdvance(inp.text()) <= inp.width()
    assert screen.status_pill.text() == "WASAPI Exclusive · 48 kHz · 24-bit"
    assert not screen.produce_btn.isEnabled()
    screen.shutdown()


def test_record_piano_then_vocal_with_guide(qapp, tmp_path):
    project = _project(tmp_path)
    screen = _screen(qapp, project)
    assert screen.selected_track == "piano"

    screen.record("piano")
    assert wait_until(qapp, lambda: screen.controller.mode == RECORDING)
    assert screen.banner.isVisible() and "MEREKAM — PIANO/ORGEN" in screen.banner_text.text()
    assert not screen.strips["bass"].isEnabled() and not screen.play_btn.isEnabled()
    assert screen.clock.property("recording") is True
    time.sleep(0.3)
    screen.stop()
    assert wait_until(qapp, lambda: project.tracks["piano"].has_audio and screen.controller.mode == IDLE)
    assert not screen.banner.isVisible()
    assert screen.strips["piano"].record.state == "terekam"
    assert screen.strips["piano"].take_button.text().startswith("Take 1 · ")
    assert screen.selected_track == "bass", "pilihan pindah ke track kosong berikutnya"

    screen.record("bass")
    assert screen.guide.isVisible(), "wizard muncul sebelum rekam vokal pertama"
    for _ in range(3):
        screen.guide.next()
    assert wait_until(qapp, lambda: screen.controller.mode == RECORDING)
    assert project.vocal_guide_done
    time.sleep(0.2)
    screen.stop()
    assert wait_until(qapp, lambda: project.tracks["bass"].has_audio and screen.controller.mode == IDLE)

    screen.record("tenor")
    assert screen.guide.isVisible(), "kelompok suara baru: gain dicek lagi"
    assert screen.guide.step == 1, "langsung di langkah Atur Gain Mic, panduan penuh hanya sekali per proyek"
    assert screen.guide.back_btn.text() == "Batal"
    screen.guide.next()
    screen.guide.next()
    assert wait_until(qapp, lambda: screen.controller.mode == RECORDING)
    time.sleep(0.2)
    screen.stop()
    assert wait_until(qapp, lambda: project.tracks["tenor"].has_audio and screen.controller.mode == IDLE)

    screen.record("tenor")
    assert not screen.guide.isVisible(), "rekam ulang suara yang sama: gain sudah diatur"
    assert wait_until(qapp, lambda: screen.controller.mode == RECORDING)
    screen.stop()
    assert wait_until(qapp, lambda: screen.controller.mode == IDLE)
    screen.shutdown()


def test_gain_check_can_be_cancelled(qapp, tmp_path):
    project = _project(tmp_path)
    screen = _screen(qapp, project)
    screen.record("piano")
    assert wait_until(qapp, lambda: screen.controller.mode == RECORDING)
    time.sleep(0.2)
    screen.stop()
    assert wait_until(qapp, lambda: project.tracks["piano"].has_audio and screen.controller.mode == IDLE)
    project.update_settings(vocal_guide_done=True)

    screen.record("alto")
    assert screen.guide.isVisible() and screen.guide.step == 1
    screen.guide.back()  # Batal
    assert wait_until(qapp, lambda: not screen.guide.isVisible())
    assert screen.controller.mode == IDLE and not project.tracks["alto"].takes
    screen.shutdown()


def test_vocal_before_piano_is_refused(qapp, tmp_path):
    screen = _screen(qapp, _project(tmp_path))
    screen.record("alto")
    assert screen.controller.mode == IDLE and not screen.guide.isVisible()
    assert "Piano" in screen.toast.text()
    screen.shutdown()


def test_device_unplugged_while_recording(qapp, tmp_path):
    project = _project(tmp_path)
    screen = _screen(qapp, project, controller_factory(die_after=200))
    screen.record("piano")
    assert wait_until(qapp, lambda: screen.error_overlay.isVisible(), timeout=10)
    msg = screen.error_overlay.message.text()
    assert msg.startswith("Sambungan ke SPL Audio SC202HD hilang saat merekam. Rekaman Piano/Orgen sampai detik 00:01")
    assert msg.endswith("sudah tersimpan dengan aman.")
    take = project.tracks["piano"].active_take
    assert take is not None and take.complete is False
    # Semua audio sampai blok terakhir tersimpan (dikurangi pergeseran kompensasi latensi).
    assert sf.info(str(project.take_path(take))).frames == 200 * BLOCK - take.latency_compensation
    assert screen.status_pill.property("ok") is False
    screen.error_overlay.reconnect.click()
    assert wait_until(qapp, lambda: not screen.error_overlay.isVisible())
    assert screen.status_pill.property("ok") is True
    screen.shutdown()


def test_play_shows_meters_and_solo_mute(qapp, tmp_path):
    project = _project(tmp_path, takes=[("piano", 3, True), ("bass", 3, True)])
    screen = _screen(qapp, project)
    screen.strips["bass"].mute.click()
    assert project.tracks["bass"].mute
    screen.play()
    assert wait_until(qapp, lambda: screen.controller.mode == PLAYING)
    assert wait_until(qapp, lambda: screen.strips["piano"].meter._db > -20)
    assert screen.strips["bass"].meter._db < -100, "track yang di-mute tidak bergerak"
    screen.strips["piano"].volume.setValue(-6)
    assert project.tracks["piano"].volume_db == -3.0
    screen.stop()
    assert wait_until(qapp, lambda: screen.controller.mode == IDLE)
    screen.shutdown()


def test_take_panel(qapp, tmp_path):
    project = _project(tmp_path, takes=[("piano", 2, True), ("bass", 2, True), ("bass", 2, True),
                                        ("bass", 1, False)])
    screen = _screen(qapp, project)
    screen._open_takes("bass")
    panel = screen._take_panel
    texts = {w.text() for w in panel.findChildren(QLabel)} | {w.text().strip() for w in panel.findChildren(QPushButton)}
    for t in ("Pilih Take — Bass", "Take lama tidak dihapus.", "Tidak lengkap", "Rekam Ulang (Take Baru)",
              "13:01 · 00:02"):
        assert t in texts, t
    panel.takeChosen.emit(1)
    assert project.tracks["bass"].active_take_id == 1
    assert screen.strips["bass"].take_button.text() == "Take 1 · 13:01"
    panel.close()
    screen.shutdown()


def test_produce_enabled_only_with_five_tracks(qapp, tmp_path):
    project = _project(tmp_path, takes=[(t, 1, True) for t in TRACK_IDS[:4]])
    screen = _screen(qapp, project)
    assert not screen.produce_btn.isEnabled() and screen.produce_hint.isVisibleTo(screen)
    number, path = project.next_take_path("sopran")
    sf.write(str(path), np.zeros((SR, 1), np.float32), SR, subtype="PCM_24")
    project.add_take("sopran", Take(number, path.name, "2026-11-06T13:01:00", 1.0))
    screen.refresh_tracks()
    assert screen.produce_btn.isEnabled() and not screen.produce_hint.isVisibleTo(screen)
    screen.room.button("aula").click()
    assert project.room_preset == "aula"
    screen.shutdown()


def test_missing_device_shows_dialog(qapp, tmp_path):
    screen = _screen(qapp, _project(tmp_path), controller_factory(connect_ok=False))
    assert screen.status_pill.text() == "Sound card tidak tersambung"
    screen.record("piano")
    assert screen.error_overlay.isVisible()
    assert screen.error_overlay.title.text() == "Sound card tidak ditemukan"
    screen.shutdown()


def test_stop_while_preparing_leaves_clean_state(qapp, tmp_path):
    project = _project(tmp_path)
    controller = controller_factory()(project, AppSettings())
    controller.connect_device()
    controller.record("piano")
    controller.stop()  # biasanya masih tahap persiapan
    assert wait_until(qapp, lambda: controller.poll().mode == IDLE and controller._pending is None)
    assert controller.record_track is None and controller.session is None
    controller.shutdown()
