"""Tes sesi rekam/putar dengan stream palsu yang meniru callback PortAudio."""

import threading
import time

import numpy as np
import pytest
import soundfile as sf

from chorale.audio.device import DeviceInfo, DeviceSelection
from chorale.audio.session import AudioSession
from chorale.project import create_project

BLOCK = 256
SELECTION = DeviceSelection(
    "Windows WASAPI",
    DeviceInfo(0, "Input (Palsu)", "Windows WASAPI", 2, 0, 48000.0),
    DeviceInfo(1, "Output (Palsu)", "Windows WASAPI", 0, 2, 48000.0),
    exclusive=True,
)


class FakeStream:
    """Memanggil callback dari thread sendiri, seperti PortAudio."""

    def __init__(self, callback, finished_callback, input_signal, die_after=None):
        self._callback = callback
        self._finished = finished_callback
        self._input = input_signal
        self._die_after = die_after
        self.output = []
        self._thread = threading.Thread(target=self._run)
        self._halt = threading.Event()

    def _run(self):
        for i, start in enumerate(range(0, len(self._input), BLOCK)):
            if self._halt.is_set() or (self._die_after is not None and i >= self._die_after):
                return
            indata = self._input[start:start + BLOCK]
            outdata = np.empty((len(indata), 2), dtype=np.float32)
            self._callback(indata, outdata, len(indata), None, None)
            self.output.append(outdata.copy())

    def start(self):
        self._thread.start()

    def wait(self):
        self._thread.join()

    def stop(self):
        self._halt.set()
        self._thread.join()

    def close(self):
        pass

    @property
    def played(self):
        return np.concatenate(self.output)


def _factory(input_signal, holder, die_after=None):
    def make(selection, callback, blocksize, finished_callback=None):
        holder.append(FakeStream(callback, finished_callback, input_signal, die_after))
        return holder[-1]
    return make


def _project(tmp_path):
    """Proyek tanpa count-in dan metronom, agar input palsu langsung terekam."""
    return create_project(tmp_path, "Lagu", count_in_bars=0, metronome_after_count_in=False)


def _run_session(project, track, input_signal, die_after=None, timeout=1.0):
    holder = []
    session = AudioSession(project, SELECTION, record_track=track, device_timeout=timeout,
                           latency_samples=0, stream_factory=_factory(input_signal, holder, die_after))
    session.start()
    holder[0].wait()
    if die_after is not None:
        time.sleep(timeout + 0.2)
    take = session.stop()
    return session, take, holder[0]


def _stereo_input(frames, left, right):
    return np.column_stack([np.full(frames, left), np.full(frames, right)]).astype(np.float32)


def test_vocal_before_piano_rejected(tmp_path):
    project = _project(tmp_path)
    with pytest.raises(ValueError, match="Piano"):
        AudioSession(project, SELECTION, record_track="bass")


def test_record_piano_then_bass_with_monitor_mix(tmp_path):
    project = _project(tmp_path)

    _, piano_take, stream = _run_session(project, "piano", _stereo_input(BLOCK * 40, 0.25, -0.125))
    assert np.all(stream.played == 0), "belum ada track lain, monitoring harus hening"
    assert project.tracks["piano"].active_take_id == piano_take.id
    piano_audio, _ = sf.read(str(project.take_path(piano_take)), dtype="float32", always_2d=True)
    assert piano_audio.shape == (BLOCK * 40, 2)
    assert piano_take.complete and piano_take.duration == pytest.approx(BLOCK * 40 / 48000, abs=1e-3)

    session, bass_take, stream = _run_session(project, "bass", _stereo_input(BLOCK * 50, 0.5, 0.9))
    played = stream.played
    assert np.allclose(played[:BLOCK * 40], piano_audio, atol=1e-6), "piano harus terdengar di headphone"
    assert np.all(played[BLOCK * 40:] == 0)
    bass_audio, _ = sf.read(str(project.take_path(bass_take)), dtype="float32", always_2d=True)
    assert bass_audio.shape == (BLOCK * 50, 1)
    assert np.allclose(bass_audio, 0.5, atol=1e-6), "bass direkam dari input 1 saja"
    assert session.dropouts == 0


def test_retake_does_not_play_old_take_of_same_track(tmp_path):
    project = _project(tmp_path)
    _run_session(project, "piano", _stereo_input(BLOCK * 20, 0.1, 0.1))
    _run_session(project, "bass", _stereo_input(BLOCK * 20, 0.4, 0.4))
    _, take2, stream = _run_session(project, "bass", _stereo_input(BLOCK * 20, 0.3, 0.3))
    assert np.allclose(stream.played, 0.1, atol=1e-6), "take bass lama tidak boleh ikut terdengar"
    assert [t.id for t in project.tracks["bass"].takes] == [1, 2]
    assert project.tracks["bass"].active_take_id == take2.id


def test_device_unplugged_keeps_audio_and_marks_incomplete(tmp_path):
    project = _project(tmp_path)
    session, take, _ = _run_session(project, "piano", _stereo_input(BLOCK * 100, 0.2, 0.2),
                                    die_after=30, timeout=0.2)
    assert take is not None and take.complete is False
    assert sf.info(str(project.take_path(take))).frames == BLOCK * 30
    assert any("terputus" in w for w in session.warnings)


def test_meter_reports_input_level(tmp_path):
    project = _project(tmp_path)
    holder = []
    session = AudioSession(project, SELECTION, record_track="piano", latency_samples=0,
                           stream_factory=_factory(_stereo_input(BLOCK * 10, 0.5, 0.05), holder))
    session.start()
    holder[0].wait()
    status = session.status()
    session.stop()
    assert status.peaks_db[0] == pytest.approx(-6.02, abs=0.01)
    assert status.peaks_db[1] == pytest.approx(-26.02, abs=0.01)
