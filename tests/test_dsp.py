"""Tes rantai pascaproduksi dengan sinyal sintetis (sinus, derau, sweep)."""

import math
import threading

import numpy as np
import pytest
import soundfile as sf

from chorale.dsp import chain
from chorale.dsp.balance import measure_lufs, balance_stem
from chorale.dsp.chain import (
    HPF_CUTOFF_HZ, ProcessingCancelled, StemInput, anti_boxiness, compress, highpass, process_project,
    process_stems,
)
from chorale.dsp.mixdown import mixdown
from chorale.dsp.reverb import (
    PRE_DELAY_S, REVERB_AMOUNTS, ROOM_PRESETS, decay_time_t30, ir_for_preset, make_ir,
)
from chorale.dsp.stereo import PAN_POSITIONS, pan_gains, place_track, stereo_width
from chorale.project import Take, create_project

SR = 48000
rng = np.random.default_rng(7)


def sine(freq, seconds=2.0, amp=0.5, channels=1):
    t = np.arange(int(seconds * SR)) / SR
    x = (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    return np.repeat(x[:, None], channels, axis=1)


def noise(seconds=3.0, amp=0.1, channels=1):
    return (amp * rng.standard_normal((int(seconds * SR), channels))).astype(np.float32)


def rms_db(x, skip=0.5):
    x = x[int(skip * SR):]
    return 20 * np.log10(np.sqrt(np.mean(x.astype(np.float64) ** 2)))


def gain_db(processed, original):
    return rms_db(processed) - rms_db(original)


# ----- tahap 2: high-pass -----

@pytest.mark.parametrize("track", list(HPF_CUTOFF_HZ))
def test_highpass_cutoffs_and_slope(track):
    fc = HPF_CUTOFF_HZ[track]
    at_fc = gain_db(highpass(sine(fc), track), sine(fc))
    one_octave = gain_db(highpass(sine(fc / 2), track), sine(fc / 2))
    two_octaves = gain_db(highpass(sine(fc / 4, seconds=4), track), sine(fc / 4, seconds=4))
    passband = gain_db(highpass(sine(fc * 8), track), sine(fc * 8))
    assert at_fc == pytest.approx(-3.0, abs=0.3)
    assert one_octave == pytest.approx(-12.3, abs=0.7)
    assert two_octaves < -22.0
    assert passband == pytest.approx(0.0, abs=0.1)


def test_hpf_cutoff_values_match_prd():
    assert HPF_CUTOFF_HZ == {"piano": 35, "bass": 75, "tenor": 75, "alto": 90, "sopran": 90}


# ----- tahap 3: EQ -----

def test_anti_boxiness_eq():
    assert gain_db(anti_boxiness(sine(400)), sine(400)) == pytest.approx(-2.0, abs=0.15)
    assert gain_db(anti_boxiness(sine(4000)), sine(4000)) == pytest.approx(0.0, abs=0.2)
    assert gain_db(anti_boxiness(sine(60)), sine(60)) == pytest.approx(0.0, abs=0.2)


# ----- tahap 4: kompresor -----

def test_compressor_reduction_never_exceeds_4db():
    quiet, loud = sine(220, 2, 0.05), sine(220, 2, 0.8)
    burst = sine(220, 0.05, 1.0)  # lonjakan sesaat
    x = np.concatenate([quiet, loud, quiet, burst, quiet])
    y, info = compress(x)
    ratio_db = 20 * np.log10(np.maximum(np.abs(y[:, 0]), 1e-9) / np.maximum(np.abs(x[:, 0]), 1e-9))
    meaningful = np.abs(x[:, 0]) > 1e-3
    assert ratio_db[meaningful].min() >= -4.0 - 1e-3
    assert info.max_reduction_db == pytest.approx(4.0, abs=1e-6)
    loud_part = slice(int(2.5 * SR), int(3.9 * SR))
    assert gain_db(y[loud_part], x[loud_part]) == pytest.approx(-4.0, abs=0.3)
    assert gain_db(y[:int(1.9 * SR)], x[:int(1.9 * SR)]) == pytest.approx(0.0, abs=0.05)


def test_compressor_ratio_and_attack():
    # Bagian 6 dB lebih pelan dari bagian terkeras: reduksi = 4 - 6*(1-1/2.5) = 0.4 dB.
    x = np.concatenate([sine(220, 2, 0.4), sine(220, 2, 0.8)])
    y, info = compress(x)
    assert gain_db(y[int(0.5 * SR):int(1.9 * SR)], x[int(0.5 * SR):int(1.9 * SR)]) == pytest.approx(-0.4, abs=0.2)
    assert info.threshold_db == pytest.approx(20 * np.log10(0.8) - 4 / 0.6, abs=0.3)
    # Attack 25 ms: 10 ms setelah lonjakan, reduksi belum penuh.
    step = 2 * SR
    early = 20 * np.log10(np.max(np.abs(y[step + 400:step + 500])) / 0.8)
    assert early > -3.5


def test_compressor_on_silence():
    y, info = compress(np.zeros((SR, 1), np.float32))
    assert np.all(y == 0) and info.max_reduction_db == 0


# ----- tahap 5: penyeimbang -----

@pytest.mark.parametrize("track,target", [("bass", -23.0), ("sopran", -23.0), ("piano", -25.0)])
@pytest.mark.parametrize("amp", [0.01, 0.1, 0.6])
def test_balance_reaches_target(track, target, amp):
    channels = 2 if track == "piano" else 1
    x = noise(4, amp, channels)
    y, info = balance_stem(x, track)
    assert measure_lufs(y) == pytest.approx(target, abs=0.5)
    assert info.target_lufs == target


def test_balance_applies_slider_offset_after_auto_gain():
    y, info = balance_stem(noise(4, 0.2), "alto", offset_db=3.0)
    assert measure_lufs(y) == pytest.approx(-20.0, abs=0.5)
    assert info.offset_db == 3.0


def test_balance_silence_is_left_alone():
    y, info = balance_stem(np.zeros((SR * 2, 1), np.float32), "tenor")
    assert np.all(y == 0) and info.auto_gain_db == 0.0


# ----- tahap 6: panning -----

@pytest.mark.parametrize("track,expected_side", [("tenor", "L"), ("sopran", "L"), ("bass", "R"), ("alto", "R")])
def test_pan_positions_and_law(track, expected_side):
    x = sine(440, 1, 0.5)
    y = place_track(x, track)
    left, right = np.max(np.abs(y[:, 0])), np.max(np.abs(y[:, 1]))
    gl, gr = pan_gains(PAN_POSITIONS[track])
    assert left / right == pytest.approx(gl / gr, rel=1e-3)
    assert (left > right) == (expected_side == "L")
    assert gl**2 + gr**2 == pytest.approx(1.0)


def test_pan_values_and_center_minus_3db():
    assert PAN_POSITIONS == {"tenor": -0.25, "sopran": -0.12, "bass": 0.12, "alto": 0.25, "piano": 0.0}
    gl, gr = pan_gains(0.0)
    assert 20 * math.log10(gl) == pytest.approx(-3.01, abs=0.01) and gl == pytest.approx(gr)
    gl, gr = pan_gains(-0.25)  # 25% kiri
    assert 20 * math.log10(gl / gr) == pytest.approx(3.49, abs=0.02)


def test_constant_power_preserves_loudness():
    x = noise(4, 0.1)
    for track in ("tenor", "alto", "bass"):
        assert measure_lufs(place_track(x, track)) == pytest.approx(measure_lufs(x), abs=0.05)


def test_piano_stereo_width_65_percent():
    x = noise(2, 0.1, 2)
    y = place_track(x, "piano")
    side_in = (x[:, 0] - x[:, 1]) / 2
    side_out = (y[:, 0] - y[:, 1]) / 2
    assert np.allclose(side_out, 0.65 * side_in, atol=1e-6)
    assert np.allclose(y[:, 0] + y[:, 1], x[:, 0] + x[:, 1], atol=1e-6)
    assert np.allclose(stereo_width(x, 1.0), x, atol=1e-6)


def test_mono_piano_centered():
    y = place_track(sine(440, 1, 0.5), "piano")
    assert np.allclose(y[:, 0], y[:, 1])


# ----- tahap 7: reverb -----

@pytest.mark.parametrize("room", list(ROOM_PRESETS))
def test_ir_decay_matches_preset(room):
    ir = ir_for_preset(room)
    target = ROOM_PRESETS[room].decay_s
    for ch in range(2):
        assert decay_time_t30(ir[:, ch]) == pytest.approx(target, rel=0.08)


def test_preset_values_match_prd():
    assert {k: v.decay_s for k, v in ROOM_PRESETS.items()} == {"gereja_kecil": 1.6, "aula": 2.0, "katedral": 2.4}
    assert REVERB_AMOUNTS["normal"] == 0.20
    assert REVERB_AMOUNTS["sedikit"] < 0.20 < REVERB_AMOUNTS["banyak"]


def test_ir_predelay_decorrelation_and_damping():
    ir = make_ir(2.4)
    pre = int(PRE_DELAY_S * SR)
    assert np.all(ir[:pre] == 0) and np.any(ir[pre:pre + 480] != 0)
    corr = np.corrcoef(ir[pre:, 0], ir[pre:, 1])[0, 1]
    assert abs(corr) < 0.05
    spectrum = np.abs(np.fft.rfft(ir[:, 0])) ** 2
    freqs = np.fft.rfftfreq(len(ir), 1 / SR)
    low = spectrum[(freqs > 500) & (freqs < 2000)].mean()
    high = spectrum[(freqs > 12000) & (freqs < 16000)].mean()
    assert 10 * np.log10(high / low) < -12
    assert np.sum(ir[:, 0].astype(np.float64) ** 2) == pytest.approx(1.0, rel=1e-4)
    assert np.array_equal(make_ir(2.4), ir), "IR harus deterministik"


def test_mixdown_length_includes_full_tail_and_wet_ratio():
    ir = ir_for_preset("aula")
    placed = {"bass": place_track(sine(220, 1), "bass"), "piano": place_track(noise(2, 0.1, 2), "piano")}
    out = mixdown(placed, ir, 0.2)
    assert len(out) == 2 * SR + len(ir) - 1
    assert np.max(np.abs(out[-SR // 10:])) < 1e-3 * np.max(np.abs(out)), "ekor berakhir mendekati -60 dB"
    dry_only = mixdown(placed, ir, 0.0)
    assert np.allclose(dry_only[:2 * SR], placed["piano"] + np.pad(placed["bass"], ((0, SR), (0, 0))), atol=1e-5)


# ----- orkestrasi -----

def _stems(seconds=3.0):
    stems = [StemInput("piano", noise(seconds, 0.1, 2))]
    stems += [StemInput(t, noise(seconds, 0.05)) for t in ("bass", "tenor", "alto", "sopran")]
    return stems


def test_process_stems_stage_order_progress_and_report():
    events = []
    result = process_stems(_stems(), progress=lambda st, pct: events.append((st, pct)))
    stages = [e[0] for e in events]
    percents = [e[1] for e in events]
    assert stages == sorted(stages) and stages[0] == 2 and stages[-1] == 7
    assert percents == sorted(percents) and percents[0] == 0 and percents[-1] == pytest.approx(100)
    assert result.tracks["piano"].stages == [2, 5, 6, 7]
    assert result.tracks["bass"].stages == [2, 3, 4, 5, 6, 7]
    assert result.mix.shape[1] == 2 and result.mix.dtype == np.float32
    assert len(result.mix) == 3 * SR + len(ir_for_preset("katedral")) - 1
    assert any("DeepFilterNet" in n for n in result.notes) or chain.denoise_module.available()


def test_denoise_stage_with_injected_denoiser_and_per_track_switch():
    called = []

    def fake_denoiser(x):
        called.append(len(x))
        return x * 0.5

    stems = _stems(1.0)
    stems[2].denoise = False  # tenor
    result = process_stems(stems, denoiser=fake_denoiser)
    assert result.tracks["bass"].stages[0] == 1
    assert 1 not in result.tracks["tenor"].stages
    assert result.tracks["tenor"].denoise_note == "dimatikan untuk track ini"
    assert 1 not in result.tracks["piano"].stages
    assert len(called) == 3
    assert not result.notes


def test_balance_inside_chain_hits_targets():
    result = process_stems(_stems(4.0))
    for tid, rep in result.tracks.items():
        assert rep.balance.target_lufs == (-25.0 if tid == "piano" else -23.0)


def test_cancel_stops_processing():
    flag = threading.Event()

    def progress(stage, pct):
        if stage >= 3:
            flag.set()

    with pytest.raises(ProcessingCancelled):
        process_stems(_stems(1.0), progress=progress, cancel=flag)


def test_invalid_presets_rejected():
    with pytest.raises(ValueError):
        process_stems(_stems(1.0), room="stadion")
    with pytest.raises(ValueError):
        process_stems(_stems(1.0), reverb_amount="sangat")
    with pytest.raises(ValueError):
        process_stems([])


def test_process_project_uses_active_takes_and_mute(tmp_path):
    project = create_project(tmp_path, "Lagu", count_in_bars=0)
    for tid, ch in (("piano", 2), ("bass", 1), ("alto", 1)):
        number, path = project.next_take_path(tid)
        sf.write(str(path), noise(2, 0.05, ch), SR, subtype="PCM_24")
        project.add_take(tid, Take(number, path.name, "2026-11-06T10:00:00", 2.0))
    project.set_mute("alto", True)
    project.update_settings(room_preset="gereja_kecil", reverb_amount="banyak")
    result = process_project(project)
    assert set(result.tracks) == {"piano", "bass"}
    assert result.excluded == ["alto"]
    assert any("Alto" in n for n in result.notes)
    assert result.room == "gereja_kecil" and result.wet == REVERB_AMOUNTS["banyak"]
