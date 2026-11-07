"""Tes pemanasan sesi rekam dan deteksi lompatan latensi stress test (temuan uji SC202HD)."""

import numpy as np
import soundfile as sf

from chorale.audio.metronome import Metronome
from chorale.audio.session import AudioSession
from chorale.project import create_project
from tests.test_session import SELECTION, FakeStream
from tools.stress_test import SR, analyze_loopback, find_jumps


def _record(tmp_path, warmup_seconds, input_signal):
    project = create_project(tmp_path, "Lagu", count_in_bars=1, metronome_after_count_in=False, tempo=120)
    holder = []

    def factory(selection, callback, blocksize, finished_callback=None):
        holder.append(FakeStream(callback, finished_callback, input_signal))
        return holder[-1]

    session = AudioSession(project, SELECTION, record_track="piano", latency_samples=0,
                           stream_factory=factory, warmup_seconds=warmup_seconds)
    assert session.warming_up == (warmup_seconds > 0)
    session.start()
    holder[0].wait()
    take = session.stop()
    return project, session, take, holder[0].played


def test_warmup_is_silent_and_not_recorded(tmp_path):
    warmup = 0.5
    n_warm = int(warmup * SR)
    frames = 5 * SR
    signal = np.zeros((frames, 2), np.float32)
    signal[:n_warm] = 0.9  # isi pemanasan berbeda dari sisanya, agar ketahuan bila ikut terekam
    signal[n_warm:] = 0.1
    project, session, take, played = _record(tmp_path, warmup, signal)
    count_in = session.count_in_frames
    assert session.warmup_frames == n_warm

    # Selama pemanasan output hening (tanpa klik hitungan awal, tanpa musik).
    assert np.max(np.abs(played[:n_warm])) == 0.0
    # Klik hitungan awal mulai tepat setelah pemanasan.
    assert np.max(np.abs(played[n_warm:n_warm + count_in])) > 0.0

    # Rekaman dimulai di frame lagu 0: setelah pemanasan dan hitungan awal, tanpa data pemanasan.
    audio, _ = sf.read(str(project.take_path(take)), dtype="float32", always_2d=True)
    assert len(audio) == frames - n_warm - count_in
    assert np.max(np.abs(audio)) < 0.5


def test_no_warmup_by_default(tmp_path):
    signal = np.full((3 * SR, 2), 0.1, np.float32)
    _, session, take, _ = _record(tmp_path, 0.0, signal)
    assert session.warmup_frames == 0 and take is not None


def test_play_only_session_ignores_warmup(tmp_path):
    project = create_project(tmp_path, "Lagu", count_in_bars=1)
    session = AudioSession(project, SELECTION, warmup_seconds=5.0, stream_factory=lambda *a, **k: None)
    assert session.warmup_frames == 0 and not session.warming_up


def test_loopback_analysis_finds_silent_latency_jump(tmp_path):
    metronome = Metronome(60, "4/4", count_in_bars=0, click_during_song=True, volume_db=-12.0)
    seconds = 40
    clicks = metronome.click_train(seconds * SR)
    rec = np.zeros(seconds * SR, np.float32)
    jump_at = 20 * SR
    rec[1000:jump_at] = clicks[:jump_at - 1000]            # jeda 1000 sampel
    rec[jump_at + 112:] = clicks[jump_at - 1000:seconds * SR - 1112]  # driver menyisipkan 112 sampel
    rng = np.random.default_rng(1)
    rec += 0.0005 * rng.standard_normal(len(rec)).astype(np.float32)
    path = tmp_path / "loopback.wav"
    sf.write(str(path), rec, SR, subtype="PCM_24")

    points = analyze_loopback(path, metronome, every_s=5.0)
    lags = [lag for _, lag in points]
    assert lags[0] == 1000 and lags[-1] == 1112
    jumps = find_jumps(points)
    assert len(jumps) == 1
    t, old, new = jumps[0]
    assert (old, new) == (1000, 1112) and 15 <= t <= 25


def test_loopback_analysis_steady_has_no_jumps(tmp_path):
    metronome = Metronome(60, "4/4", count_in_bars=0, click_during_song=True, volume_db=-12.0)
    clicks = metronome.click_train(30 * SR)
    rec = np.zeros(30 * SR, np.float32)
    rec[960:] = clicks[:-960]
    path = tmp_path / "steady.wav"
    sf.write(str(path), rec, SR, subtype="PCM_24")
    points = analyze_loopback(path, metronome, every_s=5.0)
    assert len(points) >= 4 and {lag for _, lag in points} == {960}
    assert find_jumps(points) == []
