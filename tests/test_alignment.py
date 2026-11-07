"""Tes penyejajaran take dengan kanal acuan (solusi latensi tidak tetap pada SC202HD)."""

import numpy as np
import soundfile as sf

from chorale.audio.alignment import (
    HOP, SAMPLE_RATE as SR, Segment, align_take, apply_segments, build_segments, measure_offsets,
)
from chorale.audio.session import ALIGN_CALIBRATION, ALIGN_REFERENCE, AudioSession
from chorale.project import Take, create_project
from tests.test_session import SELECTION, FakeStream


def _music(seconds: float, seed: int = 0) -> np.ndarray:
    """Sinyal mirip musik: nada-nada berganti tiap 0,4 detik ditambah derau pelan (tidak periodik)."""
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    t = np.arange(n) / SR
    out = np.zeros(n, np.float32)
    for start in range(0, n, int(0.4 * SR)):
        end = min(n, start + int(0.4 * SR))
        f = rng.uniform(110, 880)
        out[start:end] = 0.3 * np.sin(2 * np.pi * f * t[start:end])
    return (out + 0.02 * rng.standard_normal(n)).astype(np.float32)


def _delay(signal: np.ndarray, offsets: list[tuple[int, int]], length: int) -> np.ndarray:
    """out[i] = signal[i - e(i)], e berubah pada frame yang diberikan [(frame_awal, e)]."""
    out = np.zeros(length, np.float32)
    bounds = [s for s, _ in offsets[1:]] + [length]
    for (start, e), end in zip(offsets, bounds):
        idx = np.arange(start, end) - e
        ok = (idx >= 0) & (idx < len(signal))
        out[start:end][ok] = signal[idx[ok]]
    return out


def _impulses(length: int, every: int = SR // 2) -> tuple[np.ndarray, np.ndarray]:
    pos = np.arange(SR // 4, length - SR, every)
    sig = np.zeros(length, np.float32)
    sig[pos] = 0.8
    return sig, pos


def test_measure_detects_offset_and_mid_take_jump():
    played = _music(40)
    jump = 20 * SR
    ref = _delay(played, [(0, 137), (jump, 249)], len(played))
    segments = build_segments(measure_offsets(ref, played))
    assert [s.offset for s in segments] == [137, 249]
    assert abs(segments[1].start - jump) <= 2 * HOP


def test_small_alternating_measurement_noise_is_not_a_jump():
    """Pola nyata dari SC202HD: e bergantian 50/61 karena klik aksen dan biasa berbeda nada."""
    points = [(i * HOP, e) for i, e in enumerate([50, 61, 61, 50, 50, 61, 61, 50, 50, 61, 61, 50])]
    segments = build_segments(points)
    assert len(segments) == 1 and 50 <= segments[0].offset <= 61


def test_apply_segments_puts_vocal_back_on_the_grid():
    n = 30 * SR
    vocal, pos = _impulses(n)
    jump = 15 * SR + 1234
    recorded = _delay(vocal, [(0, 300), (jump, 412)], n)
    aligned = apply_segments(recorded[:, None], (Segment(0, 300), Segment(jump - 300, 412)))[:, 0]
    found = np.flatnonzero(aligned > 0.4)
    near_cut = np.abs(pos - (jump - 300)) < SR // 50
    assert set(pos[~near_cut]) <= set(found)
    assert len(aligned) == n - 412


def test_negative_offset_pads_start():
    audio = np.arange(10, dtype=np.float32)[:, None]
    out = apply_segments(audio, (Segment(0, -3),))[:, 0]
    assert list(out[:3]) == [0, 0, 0] and list(out[3:6]) == [0, 1, 2] and len(out) == 13


def test_silent_reference_is_not_detected():
    played = _music(5)
    assert build_segments(measure_offsets(np.zeros(5 * SR, np.float32), played)) is None


def test_align_take_rewrites_file_atomically(tmp_path):
    played = _music(12, seed=3)
    vocal, pos = _impulses(len(played))
    take = tmp_path / "bass_take1_20261107-120000.wav"
    ref = tmp_path / "bass_take1_20261107-120000_acuan.wav"
    sf.write(str(take), _delay(vocal, [(0, 500)], len(played)), SR, subtype="PCM_24")
    sf.write(str(ref), _delay(played, [(0, 500)], len(played)), SR, subtype="PCM_24")
    result = align_take(take, ref, played)
    assert result is not None and result.offset == 500 and result.jumps == 0
    audio, _ = sf.read(str(take), dtype="float32")
    assert set(pos) <= set(np.flatnonzero(audio > 0.4))
    assert not list(tmp_path.glob("*.tmp"))


def _project_with_piano(tmp_path, seconds=2.5):
    """Piano pendek: stream palsu menyuap audio tanpa jeda waktu nyata, ring buffer perekam hanya 4 detik."""
    project = create_project(tmp_path, "Lagu", count_in_bars=0, metronome_after_count_in=False)
    number, path = project.next_take_path("piano")
    piano = _music(seconds, seed=7)
    sf.write(str(path), np.stack([piano, piano], axis=1), SR, subtype="PCM_24")
    project.add_take("piano", Take(number, path.name, "2026-11-07T12:00:00", seconds))
    return project


def _record_vocal(project, true_latency: int, reference_ok: bool = True):
    """Rekam bass dengan stream palsu: latensi sebenarnya `true_latency`, kalibrasi bilang 0."""
    holder = []
    session_box = []

    def factory(selection, callback, blocksize, finished_callback=None):
        session = session_box[0]
        n = int(session.playback_length_seconds * SR) + SR
        played = session.played_reference(n)
        vocal, _ = _impulses(n)
        mic = _delay(vocal, [(0, true_latency)], n)        # penyanyi mengikuti playback yang tertunda
        ref = _delay(played, [(0, true_latency)], n) if reference_ok else np.zeros(n, np.float32)
        holder.append(FakeStream(callback, finished_callback, np.stack([mic, ref], axis=1)))
        return holder[-1]

    session = AudioSession(project, SELECTION, record_track="bass", record_channels=1, latency_samples=0,
                           reference_channel=1, stream_factory=factory)
    session_box.append(session)
    session.start()
    holder[0].wait()
    take = session.stop()
    return session, take


def test_session_aligns_vocal_take_with_reference(tmp_path):
    project = _project_with_piano(tmp_path)
    session, take = _record_vocal(project, true_latency=731)
    assert session.recorder.overrun_frames == 0 and session.reference_recorder.overrun_frames == 0
    assert take.alignment == ALIGN_REFERENCE and take.latency_compensation == 731
    audio, _ = sf.read(str(project.take_path(take)), dtype="float32")
    _, pos = _impulses(len(audio) + 731)
    pos = pos[pos < len(audio)]
    assert set(pos) <= set(np.flatnonzero(audio > 0.4))
    assert not list(project.takes_dir.glob("*_acuan.wav")), "berkas acuan harus dihapus"
    assert session.warnings == []


def test_session_falls_back_to_calibration_without_reference_signal(tmp_path):
    project = _project_with_piano(tmp_path)
    session, take = _record_vocal(project, true_latency=731, reference_ok=False)
    assert take.alignment == ALIGN_CALIBRATION and take.latency_compensation == 0
    assert any("Kanal acuan tidak terdeteksi" in w for w in session.warnings)
    assert not list(project.takes_dir.glob("*_acuan.wav"))


def test_reference_channel_must_differ_from_recorded_channel(tmp_path):
    project = _project_with_piano(tmp_path)
    try:
        AudioSession(project, SELECTION, record_track="bass", record_channels=1, reference_channel=0,
                     stream_factory=lambda *a, **k: None)
    except ValueError as exc:
        assert "Kanal acuan" in str(exc)
    else:
        raise AssertionError("kanal acuan yang sama dengan mikrofon harus ditolak")
