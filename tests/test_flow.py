"""Alur non-UI: proyek berisi 5 take sintetis -> produce() -> 3 file ekspor valid; pembatalan; A/B."""

import threading
import time
from datetime import datetime

import numpy as np
import pytest
import soundfile as sf

from chorale.audio.ab_player import SOURCE_A, SOURCE_B, ABPlayer
from chorale.audio.device import DeviceInfo, DeviceSelection
from chorale.dsp.errors import ProcessingCancelled
from chorale.dsp.export import decode_audio
from chorale.dsp.measure import integrated_lufs, run_ffmpeg, true_peak_db
from chorale.dsp.produce import produce
from chorale.project import TRACK_IDS, create_project, open_project
from tools.import_takes import import_demo, import_take

SR = 48000
SELECTION = DeviceSelection(
    "Windows WASAPI", DeviceInfo(0, "Line (X)", "Windows WASAPI", 2, 0, 48000.0),
    DeviceInfo(1, "Speakers (X)", "Windows WASAPI", 0, 2, 48000.0), True)


@pytest.fixture(scope="module")
def full_project(tmp_path_factory):
    project = create_project(tmp_path_factory.mktemp("alur"), "Kudus, Kudus, Kudus", tempo=72)
    import_demo(project, bars=4)
    return project


def test_import_take_converts_format(tmp_path):
    project = create_project(tmp_path, "Impor")
    take = import_take(project, "piano", 0.1 * np.ones(44100, np.float32), 44100)
    info = sf.info(str(project.take_path(take)))
    assert (info.samplerate, info.channels, info.subtype) == (48000, 2, "PCM_24")
    assert info.frames == pytest.approx(48000, abs=2)
    vocal = import_take(project, "bass", 0.1 * np.ones((48000, 2), np.float32))
    assert sf.info(str(project.take_path(vocal))).channels == 1
    assert open_project(project.folder).tracks["piano"].active_take_id == take.id


def test_full_flow_produces_three_valid_files(full_project):
    assert all(full_project.tracks[t].has_audio for t in TRACK_IDS)
    result = produce(full_project, verify=True, when=datetime(2026, 11, 6, 13, 5))
    stem = "Kudus,_Kudus,_Kudus_20261106-1305"  # koma diizinkan Windows, jadi tetap ada
    assert [p.name for p in (result.wav_path, result.mp3_path, result.report_path)] == [
        f"{stem}_Master.wav", f"{stem}_Master.mp3", f"{stem}_Laporan.txt"]
    files = sorted(p.name for p in full_project.master_dir.iterdir())
    assert files == sorted([f"{stem}_Laporan.txt", f"{stem}_Master.mp3", f"{stem}_Master.wav"])

    info = sf.info(str(result.wav_path))
    assert (info.samplerate, info.channels, info.subtype) == (48000, 2, "PCM_24")
    wav, _ = sf.read(str(result.wav_path), dtype="float32")
    assert true_peak_db(wav) <= -1.0
    assert integrated_lufs(wav) == pytest.approx(-14.0, abs=1.0)
    mp3 = decode_audio(result.mp3_path)
    assert abs(len(mp3) - len(wav)) < SR // 10 and true_peak_db(mp3) <= -1.0
    report = result.report_path.read_text(encoding="utf-8")
    for word in ("Kelantangan", "True Peak", "LRA", "Durasi", "Reduksi limiter", "Ruang"):
        assert word in report
    assert result.youtube_ready and result.verification.ok


def test_cancel_during_export_removes_partial_files(tmp_path):
    project = create_project(tmp_path, "Batal")
    import_demo(project, bars=2)
    cancel = threading.Event()

    def progress(step, pct):
        if step == 7 and pct >= 90:  # WAV sudah tertulis, MP3 belum
            cancel.set()

    with pytest.raises(ProcessingCancelled):
        produce(project, progress=progress, cancel=cancel)
    assert list(project.master_dir.iterdir()) == []


def test_ffmpeg_can_be_stopped_midway():
    cancel = threading.Event()
    threading.Timer(0.4, cancel.set).start()
    start = time.monotonic()
    with pytest.raises(ProcessingCancelled):
        run_ffmpeg(["-hide_banner", "-loglevel", "error", "-re", "-f", "lavfi", "-i", "anoisesrc=d=30",
                    "-f", "null", "-"], cancel)
    assert time.monotonic() - start < 5


class FakeOutput:
    def __init__(self, callback):
        self.callback, self._halt = callback, threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self._halt.is_set():
            out = np.empty((256, 2), np.float32)
            self.callback(out, 256, None, None)
            self.last = out
            time.sleep(0.0005)

    def start(self):
        self._thread.start()

    def stop(self):
        self._halt.set()
        self._thread.join(2)

    def close(self):
        pass


def test_ab_player_switches_without_losing_position():
    raw = np.full((SR * 4, 2), 0.1, np.float32)
    master = np.full((SR * 4, 2), 0.4, np.float32)
    streams = []
    player = ABPlayer(SELECTION, raw, master, 0.0, -6.0,
                      stream_factory=lambda sel, cb, bs: streams.append(FakeOutput(cb)) or streams[-1])
    player.play()
    time.sleep(0.15)
    pos = player.position_seconds
    assert pos > 0 and player.source == SOURCE_B
    assert np.allclose(streams[0].last, 0.4 * 10 ** (-6 / 20), atol=1e-6)
    player.set_source(SOURCE_A)
    time.sleep(0.05)
    assert player.position_seconds >= pos, "posisi tidak kembali ke awal saat pindah A/B"
    assert np.allclose(streams[0].last, 0.1, atol=1e-6)
    player.pause()
    paused = player.position_seconds
    time.sleep(0.05)
    assert player.position_seconds == paused and not player.playing
    player.seek(10)
    assert player.position_seconds == pytest.approx(4.0)
    assert player.ended
    player.close()
