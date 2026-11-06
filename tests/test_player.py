"""Tes mixer monitoring, pemutar, dan level meter dengan sinyal sintetis."""

import numpy as np
import pytest

from chorale.audio.meter import LevelMeter, meter_zone, to_dbfs
from chorale.audio.player import Player, TrackAudio, db_to_gain, mix_tracks


def _const(track_id, value, frames=100, channels=1, **kw):
    return TrackAudio(track_id, np.full((frames, channels), value, dtype=np.float32), **kw)


def _tracks(**overrides):
    # Nilai tiap track unik (pangkat 2) agar kontribusinya bisa dibedakan dari jumlahnya.
    values = {"piano": 0.01, "bass": 0.02, "tenor": 0.04, "alto": 0.08, "sopran": 0.16}
    return [_const(t, v, channels=2 if t == "piano" else 1, **overrides.get(t, {}))
            for t, v in values.items()]


def test_all_tracks_mixed_mono_centered():
    mix = mix_tracks(_tracks())
    assert mix.shape == (100, 2)
    assert np.allclose(mix, 0.31)


def test_mute_removes_track():
    mix = mix_tracks(_tracks(alto={"mute": True}))
    assert np.allclose(mix, 0.31 - 0.08)


def test_solo_plays_only_soloed():
    mix = mix_tracks(_tracks(bass={"solo": True}, sopran={"solo": True}))
    assert np.allclose(mix, 0.02 + 0.16)


def test_mute_wins_over_solo():
    mix = mix_tracks(_tracks(bass={"solo": True, "mute": True}, tenor={"solo": True}))
    assert np.allclose(mix, 0.04)


def test_volume_offset_applied():
    mix = mix_tracks(_tracks(piano={"volume_db": 6.0}))
    assert np.allclose(mix, 0.01 * db_to_gain(6.0) + 0.30)
    assert db_to_gain(-6.0) == pytest.approx(0.501187, rel=1e-5)


def test_recorded_track_excluded_even_if_soloed():
    mix = mix_tracks(_tracks(alto={"solo": True}), exclude="alto")
    assert np.allclose(mix, 0.31 - 0.08)


def test_stereo_channels_kept_separate():
    piano = TrackAudio("piano", np.column_stack([np.full(10, 0.1), np.full(10, -0.2)]).astype(np.float32))
    mix = mix_tracks([piano])
    assert np.allclose(mix[:, 0], 0.1) and np.allclose(mix[:, 1], -0.2)


def test_different_lengths_padded_with_silence():
    mix = mix_tracks([_const("piano", 0.1, frames=50, channels=2), _const("bass", 0.2, frames=80)])
    assert len(mix) == 80
    assert np.allclose(mix[:50], 0.3) and np.allclose(mix[50:], 0.2)


def test_empty_mix():
    assert mix_tracks([]).shape == (0, 2)


def test_player_blocks_and_silence_after_end():
    mix = np.arange(1000, dtype=np.float32).repeat(2).reshape(-1, 2)
    player = Player(mix)
    out = np.empty((256, 2), dtype=np.float32)
    collected = []
    for _ in range(5):
        player.process_output(out)
        collected.append(out.copy())
    played = np.concatenate(collected)
    assert np.array_equal(played[:1000], mix)
    assert np.all(played[1000:] == 0)
    assert player.finished and player.position_frames == 1280


def test_meter_peak_hold_and_reset():
    m = LevelMeter(2)
    m.update(np.array([[0.1, -0.5], [-0.3, 0.2]], dtype=np.float32))
    m.update(np.array([[0.05, 0.1]], dtype=np.float32))
    assert np.allclose(m.read(), [0.3, 0.5])
    m.update(np.array([[0.01, 0.02]], dtype=np.float32))
    assert np.allclose(m.read(), [0.01, 0.02])


def test_meter_clip_latches_until_reset():
    m = LevelMeter(2)
    m.update(np.array([[1.0, 0.1]], dtype=np.float32))
    m.read()
    m.update(np.zeros((4, 2), dtype=np.float32))
    assert m.clip().tolist() == [True, False]
    m.reset_clip(0)
    assert m.clip().tolist() == [False, False]


@pytest.mark.parametrize("db,zone", [(-50, "kosong"), (-42, "hijau"), (-12.5, "hijau"),
                                     (-12, "hijau"), (-6, "kuning"), (-3, "kuning"), (-1, "merah")])
def test_meter_zones(db, zone):
    assert meter_zone(db) == zone


def test_to_dbfs():
    assert to_dbfs(1.0) == pytest.approx(0.0)
    assert to_dbfs(0.0) == -120.0
