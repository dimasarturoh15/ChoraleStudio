"""Tes metronom: posisi tepat per sampel, count-in, aksen, volume."""

import numpy as np
import pytest

from chorale.audio.metronome import ACCENT_FREQ, BEAT_FREQ, Metronome, make_click

SR = 48000


def _expected(m: Metronome, start: int, frames: int, gain: float) -> np.ndarray:
    """Bangun ulang klik secara langsung dari rumus round(k * spb)."""
    out = np.zeros(frames, dtype=np.float32)
    hi, lo = make_click(ACCENT_FREQ) * gain, make_click(BEAT_FREQ) * gain
    for k in range(-m.count_in_beats, 10_000):
        pos = round(k * m.samples_per_beat) - start
        if pos >= frames:
            break
        if k >= 0 and not m.click_during_song:
            break
        click = hi if k % m.beats_per_bar == 0 else lo
        a, b = max(0, pos), min(frames, pos + len(click))
        if a < b:
            out[a:b] += click[a - pos:b - pos]
    return out


def _render_blocks(m: Metronome, start: int, frames: int, block: int) -> np.ndarray:
    out = np.zeros((frames, 2), dtype=np.float32)
    for i in range(0, frames, block):
        m.render(out[i:i + block], start + i)
    assert np.array_equal(out[:, 0], out[:, 1])
    return out[:, 0]


@pytest.mark.parametrize("tempo", [40, 70, 72, 97, 240])
@pytest.mark.parametrize("block", [128, 256, 1024, 333])
def test_sample_accurate_and_block_independent(tempo, block):
    m = Metronome(tempo, "4/4", count_in_bars=2, volume_db=0.0)
    start = -m.count_in_frames
    frames = m.count_in_frames + 5 * SR
    rendered = _render_blocks(m, start, frames, block)
    assert np.allclose(rendered, _expected(m, start, frames, 1.0), atol=1e-6)


def test_no_drift_after_long_time():
    m = Metronome(97, "3/4", volume_db=0.0)  # 29690,72... sampel per ketukan
    k = 97 * 60  # ketukan setelah 60 menit
    pos = m.beat_frame(k)
    assert pos == round(k * 60 * SR / 97)
    out = np.zeros((2000, 1), dtype=np.float32)
    m.render(out, pos - 1000)
    assert np.all(out[:1000] == 0) and np.any(out[1001:1100] != 0)


def test_count_in_length_and_song_zero():
    m = Metronome(72, "4/4", count_in_bars=2)
    assert m.count_in_frames == 8 * 40000
    assert Metronome(72, "6/8", count_in_bars=1).count_in_frames == 6 * 40000
    assert Metronome(72, "4/4", count_in_bars=0).count_in_frames == 0


def test_click_stops_after_count_in_when_disabled():
    m = Metronome(120, "4/4", count_in_bars=1, click_during_song=False)
    count_in = _render_blocks(m, -m.count_in_frames, m.count_in_frames, 256)
    song = _render_blocks(m, 0, 4 * SR, 256)
    assert np.count_nonzero(count_in) > 0
    assert np.count_nonzero(song) == 0


def test_no_clicks_before_count_in():
    m = Metronome(120, "4/4", count_in_bars=1)
    before = _render_blocks(m, -m.count_in_frames - 3 * SR, 3 * SR, 256)
    assert np.count_nonzero(before) == 0


def test_first_beat_of_bar_is_accented():
    m = Metronome(120, "3/4", volume_db=0.0)
    n = len(make_click(ACCENT_FREQ))
    out = _render_blocks(m, 0, 4 * 24000, 256)
    assert np.allclose(out[:n], make_click(ACCENT_FREQ))
    assert np.allclose(out[24000:24000 + n], make_click(BEAT_FREQ))
    assert np.allclose(out[3 * 24000:3 * 24000 + n], make_click(ACCENT_FREQ))


def test_volume_is_separate():
    loud = _render_blocks(Metronome(120, "4/4", volume_db=0.0), 0, SR, 256)
    soft = _render_blocks(Metronome(120, "4/4", volume_db=-20.0), 0, SR, 256)
    assert np.max(np.abs(soft)) == pytest.approx(np.max(np.abs(loud)) * 0.1, rel=1e-4)


def test_render_adds_on_top_of_music():
    m = Metronome(120, "4/4", volume_db=0.0)
    out = np.full((512, 2), 0.25, dtype=np.float32)
    m.render(out, 0)
    assert np.allclose(out[:, 0] - 0.25, m.click_train(512))


def test_unknown_time_signature():
    with pytest.raises(ValueError):
        Metronome(100, "5/4")
