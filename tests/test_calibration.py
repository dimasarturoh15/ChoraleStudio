"""Tes logika kalibrasi latensi (tanpa perangkat audio)."""

import numpy as np
import pytest

from chorale.audio.calibration import (
    CalibrationResult,
    estimate_delay,
    load_calibrations,
    make_sweep,
    save_calibration,
)

SR = 48000


def _loopback(stimulus, delay, gain=0.3, noise=0.001, seed=0):
    rng = np.random.default_rng(seed)
    out = np.zeros(len(stimulus) + delay + 1000, dtype=np.float32)
    out[delay:delay + len(stimulus)] = gain * stimulus
    return out + noise * rng.standard_normal(len(out)).astype(np.float32)


def test_sweep_shape_and_level():
    s = make_sweep(SR)
    assert s.dtype == np.float32
    assert len(s) == SR // 2
    assert np.max(np.abs(s)) <= 0.5 + 1e-6
    assert abs(s[0]) < 1e-3 and abs(s[-1]) < 1e-3


@pytest.mark.parametrize("delay", [0, 1, 37, 512, 1234, 9600])
def test_estimate_delay_exact(delay):
    stim = np.concatenate([np.zeros(1000, np.float32), make_sweep(SR)])
    est = estimate_delay(_loopback(stim, delay), stim)
    assert est.lag_samples == delay
    assert abs(est.lag_fractional - delay) < 0.5
    assert est.quality > 20
    assert not est.inverted


def test_estimate_delay_inverted_polarity():
    stim = make_sweep(SR)
    est = estimate_delay(-_loopback(stim, 700), stim)
    assert est.lag_samples == 700
    assert est.inverted


def test_low_quality_when_signal_missing():
    stim = make_sweep(SR)
    rng = np.random.default_rng(1)
    noise = 0.01 * rng.standard_normal(len(stim) + 5000)
    assert estimate_delay(noise, stim).quality < 20


def _result(blocksize=256, latency=600):
    return CalibrationResult(
        input_device="In", output_device="Out", hostapi="Windows WASAPI", exclusive=True,
        samplerate=SR, blocksize=blocksize, latency_samples=latency, latency_ms=latency / SR * 1000,
        runs_samples=[latency] * 5, date="2026-11-06T10:00:00",
    )


def test_save_and_replace_same_key(tmp_path):
    path = tmp_path / "sub" / "calibration.json"
    save_calibration(_result(latency=600), path)
    save_calibration(_result(latency=610), path)
    save_calibration(_result(blocksize=512, latency=900), path)
    entries = load_calibrations(path)
    assert len(entries) == 2
    by_block = {e.blocksize: e.latency_samples for e in entries}
    assert by_block == {256: 610, 512: 900}


def test_load_missing_file(tmp_path):
    assert load_calibrations(tmp_path / "tidak_ada.json") == []
