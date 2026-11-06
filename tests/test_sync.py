"""Simulasi kabel loopback: 5 track direkam berurutan harus sejajar sampel-per-sampel.

Stream palsu mengembalikan output ke input dengan jeda L sampel, persis seperti
kabel loopback dari output ke input sound card dengan latensi round-trip L.
"""

import threading

import numpy as np
import pytest
import soundfile as sf

from chorale.audio.calibration import CalibrationResult, estimate_delay, save_calibration
from chorale.audio.device import DeviceInfo, DeviceSelection
from chorale.audio.metronome import Metronome
from chorale.audio.session import AudioSession
from chorale.project import TRACK_IDS, create_project

BLOCK = 256
L = 777  # latensi round-trip palsu (sampel)
GAIN = 0.5
SELECTION = DeviceSelection(
    "Windows WASAPI",
    DeviceInfo(0, "Input (Palsu)", "Windows WASAPI", 2, 0, 48000.0),
    DeviceInfo(1, "Output (Palsu)", "Windows WASAPI", 0, 2, 48000.0),
    exclusive=True,
)


class LoopbackStream:
    """Input = output L sampel sebelumnya (dikali GAIN); berjalan sejumlah frame tertentu."""

    def __init__(self, callback, total_frames, latency=L, reported=(0.004, 0.006), connected=True):
        self._callback = callback
        self._total = total_frames
        self._latency = latency
        self._connected = connected
        self.latency = reported
        self.history = np.zeros((total_frames + BLOCK, 2), dtype=np.float32)
        self._thread = threading.Thread(target=self._run)

    def _run(self):
        for t0 in range(0, self._total, BLOCK):
            src = t0 - self._latency
            indata = np.zeros((BLOCK, 2), dtype=np.float32)
            if self._connected and src + BLOCK > 0:
                a = max(0, -src)
                indata[a:] = GAIN * self.history[src + a:src + BLOCK]
            outdata = np.empty((BLOCK, 2), dtype=np.float32)
            self._callback(indata, outdata, BLOCK, None, None)
            self.history[t0:t0 + BLOCK] = outdata

    def start(self):
        self._thread.start()

    def wait(self):
        self._thread.join()

    def stop(self):
        self._thread.join()

    def close(self):
        pass


def _record(project, track, seconds, **session_kw):
    holder = []
    cfg = {k: session_kw.pop(k) for k in ("latency", "reported", "connected") if k in session_kw}

    def factory(selection, callback, blocksize, finished_callback=None):
        count_in = holder_session[0].count_in_frames
        total = count_in + int(seconds * 48000)
        holder.append(LoopbackStream(callback, total, **cfg))
        return holder[-1]

    holder_session = []
    session = AudioSession(project, SELECTION, record_track=track, stream_factory=factory, **session_kw)
    holder_session.append(session)
    session.start()
    holder[0].wait()
    take = session.stop()
    return session, take, holder[0]


def _project(tmp_path, **kw):
    settings = dict(tempo=120, time_signature="4/4", count_in_bars=1, metronome_after_count_in=True)
    settings.update(kw)
    return create_project(tmp_path, "Uji Sinkron", **settings)


def _offset(project, track, metronome):
    audio, _ = sf.read(str(project.take_path(project.tracks[track].active_take)), dtype="float32",
                       always_2d=True)
    reference = metronome.click_train(len(audio) + 2000)
    est = estimate_delay(audio[:, 0], reference)
    assert est.quality > 20
    return est.lag_fractional


def test_five_tracks_aligned_with_latency_compensation(tmp_path):
    project = _project(tmp_path)
    ref = Metronome(120, "4/4", count_in_bars=0, click_during_song=True)
    # Piano merekam klik metronom lewat loopback; vokal mendengar track sebelumnya (metronom mati).
    _record(project, "piano", 6, latency_samples=L)
    for track in TRACK_IDS[1:]:
        _record(project, track, 6, latency_samples=L, metronome=False)

    offsets = {t: _offset(project, t, ref) for t in TRACK_IDS}
    assert all(abs(o) < 0.5 for o in offsets.values()), offsets
    for t in TRACK_IDS:
        take = project.tracks[t].active_take
        assert take.latency_compensation == L
        assert take.complete


def test_without_compensation_tracks_drift_apart(tmp_path):
    """Kontrol: tanpa kompensasi, piano telat L dan setiap generasi bertambah telat."""
    project = _project(tmp_path)
    ref = Metronome(120, "4/4")
    _record(project, "piano", 4, latency_samples=0)
    _record(project, "bass", 4, latency_samples=0, metronome=False)
    assert _offset(project, "piano", ref) == pytest.approx(L, abs=0.5)
    assert _offset(project, "bass", ref) == pytest.approx(2 * L, abs=0.5)


def test_count_in_and_metronome_never_recorded(tmp_path):
    project = _project(tmp_path, count_in_bars=2)
    session, take, stream = _record(project, "piano", 3, latency_samples=L, connected=False)
    audio, _ = sf.read(str(project.take_path(take)), dtype="float32")
    assert np.all(audio == 0), "klik metronom tidak boleh masuk ke file rekaman"
    assert np.count_nonzero(stream.history) > 0, "klik harus terdengar di headphone"
    # Rekaman dimulai di 00:00 lagu (setelah 2 bar count-in) + kompensasi latensi.
    total = session.count_in_frames + 3 * 48000
    rounded = -(-total // BLOCK) * BLOCK
    assert len(audio) == rounded - session.count_in_frames - L


def test_count_in_clicks_precede_song_zero(tmp_path):
    project = _project(tmp_path, count_in_bars=1, metronome_after_count_in=False)
    session, _, stream = _record(project, "piano", 2, latency_samples=0)
    out = stream.history[:, 0]
    ci = session.count_in_frames
    assert ci == 4 * 24000
    assert np.count_nonzero(out[:ci]) > 0
    assert np.count_nonzero(out[ci:ci + 2 * 48000]) == 0, "metronom berhenti setelah count-in"


def test_uses_saved_calibration(tmp_path):
    save_calibration(CalibrationResult(
        input_device="Input (Palsu)", output_device="Output (Palsu)", hostapi="Windows WASAPI",
        exclusive=True, samplerate=48000, blocksize=256, latency_samples=L, latency_ms=L / 48,
    ))
    project = _project(tmp_path)
    session, take, _ = _record(project, "piano", 3)
    assert session.latency_source == "kalibrasi"
    assert take.latency_compensation == L
    assert not session.warnings
    assert abs(_offset(project, "piano", Metronome(120, "4/4"))) < 0.5


def test_without_calibration_uses_driver_latency_and_warns(tmp_path):
    project = _project(tmp_path)
    session, take, _ = _record(project, "piano", 3, reported=(0.004, 0.006))
    assert session.latency_source == "perkiraan driver"
    assert take.latency_compensation == 480
    assert any("Belum ada kalibrasi" in w for w in session.warnings)


def test_short_vocal_take_marked_incomplete(tmp_path):
    project = _project(tmp_path)
    _record(project, "piano", 4, latency_samples=0)
    session, short, _ = _record(project, "alto", 3, latency_samples=0, metronome=False)
    assert short.complete is False
    assert any("90%" in w for w in session.warnings)
    _, full, _ = _record(project, "alto", 3.8, latency_samples=0, metronome=False)
    assert full.complete is True
