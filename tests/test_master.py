"""Tes pengukuran, mastering, ekspor, dan produce() (PRD FR-7, FR-8, Bagian 10)."""

import re
import subprocess
import threading
from datetime import datetime

import numpy as np
import pytest
import soundfile as sf

from chorale.dsp.chain import ProcessingCancelled
from chorale.dsp.export import (
    base_name, clean_title, decode_audio, encode_mp3, to_pcm24_tpdf, trim_tail, write_wav,
)
from chorale.dsp.master import (
    CEILING_DBTP, limiter_gain_db, loudness_matched_gains, master,
)
from chorale.dsp.measure import (
    cross_check, fast_integrated_lufs, ffmpeg_exe, integrated_lufs, loudness_range, oversampled_peaks,
    true_peak_db,
)
from chorale.dsp.produce import STEP_LABELS, produce
from tools.make_demo_project import create_demo

SR = 48000
rng = np.random.default_rng(11)


def stereo(x):
    return np.repeat(np.asarray(x, dtype=np.float32)[:, None], 2, axis=1)


def sine(freq, seconds=5.0, amp=0.5, phase=0.0):
    t = np.arange(int(seconds * SR)) / SR
    return stereo(amp * np.sin(2 * np.pi * freq * t + phase))


def pink_noise(seconds, amp=0.1):
    white = rng.standard_normal((int(seconds * SR), 2))
    spectrum = np.fft.rfft(white, axis=0)
    f = np.fft.rfftfreq(len(white), 1 / SR)
    spectrum[1:] /= np.sqrt(f[1:, None])
    x = np.fft.irfft(spectrum, n=len(white), axis=0)
    return (amp * x / np.std(x)).astype(np.float32)


def music_like(seconds=20.0):
    """Derau merah muda dengan selubung frase (naik-turun tiap 2 detik)."""
    x = pink_noise(seconds, 0.1)
    t = np.arange(len(x)) / SR
    env = 0.55 + 0.45 * np.sin(2 * np.pi * t / 4.0) ** 2
    return (x * env[:, None]).astype(np.float32)


# ----- pengukuran -----

def test_lufs_reference_sine_minus_23():
    # EBU Tech 3341: sinus 1 kHz stereo -23 dBFS = -23 LUFS.
    x = sine(1000, 20, 10 ** (-23 / 20))
    assert integrated_lufs(x) == pytest.approx(-23.0, abs=0.1)
    assert fast_integrated_lufs(x) == pytest.approx(-23.0, abs=0.1)


def test_fast_lufs_matches_pyloudnorm():
    for x in (music_like(15), pink_noise(10, 0.3), sine(200, 5, 0.1)):
        assert fast_integrated_lufs(x) == pytest.approx(integrated_lufs(x), abs=0.1)


@pytest.mark.parametrize("freq,phase", [(997, 0.1), (6000, 0.7), (12000, np.pi / 4), (16000, np.pi / 6), (19000, 0.3)])
def test_true_peak_accuracy(freq, phase):
    tp = true_peak_db(sine(freq, 2, 0.5, phase))
    # Nilai sebenarnya -6,02 dBTP; boleh sedikit lebih tinggi (aman), tidak boleh jauh lebih rendah.
    assert -6.12 <= tp <= -5.70


def test_true_peak_sees_intersample_peak():
    x = sine(12000, 2, 0.5, np.pi / 4)
    sample_peak = 20 * np.log10(np.abs(x).max())
    assert sample_peak == pytest.approx(-9.03, abs=0.01)
    assert true_peak_db(x) > sample_peak + 2.5


def test_lra_ebu_3342_style():
    # 20 s pada -20 LUFS lalu 20 s pada -30 LUFS -> LRA sekitar 10 LU.
    a, b = sine(1000, 20, 10 ** (-20 / 20)), sine(1000, 20, 10 ** (-30 / 20))
    assert loudness_range(np.concatenate([a, b])) == pytest.approx(10.0, abs=1.0)
    assert loudness_range(sine(1000, 20, 0.1)) == pytest.approx(0.0, abs=0.1)


@pytest.mark.parametrize("make", [lambda: music_like(15), lambda: pink_noise(10, 0.2), lambda: sine(997, 8, 0.5)])
def test_cross_check_with_ffmpeg(make):
    check = cross_check(make())
    assert check.ok, (check.ours, check.ffmpeg)
    assert check.lra_diff <= 1.0


# ----- limiter & mastering -----

def test_limiter_curve_never_exceeds_need():
    x = music_like(5) * 4
    peaks = oversampled_peaks(x)
    curve = limiter_gain_db(peaks, -1.0)
    need = np.minimum(0.0, -1.0 - 20 * np.log10(np.maximum(peaks.astype(np.float64), 1e-12)))
    assert np.all(curve <= need + 1e-9)


def _hard_transients(seconds=10.0):
    x = 0.02 * rng.standard_normal((int(seconds * SR), 2)).astype(np.float32)
    x[:: SR // 3] = 0.99
    x[SR // 7:: SR // 2] = -0.99
    return x


SIGNALS = {
    "musik": lambda: music_like(20),
    "transien keras": _hard_transients,
    "gelombang kotak": lambda: stereo(0.9 * np.sign(np.sin(2 * np.pi * 220 * np.arange(10 * SR) / SR))),
    "sinus 12 kHz antar-sampel": lambda: sine(12000, 5, 0.9, np.pi / 4),
    "sweep": lambda: stereo(0.8 * np.sin(2 * np.pi * np.cumsum(np.geomspace(20, 20000, 10 * SR)) / SR)),
    "ledakan tiba-tiba": lambda: np.concatenate([music_like(8) * 0.05, pink_noise(0.3, 0.9), music_like(8) * 0.05]),
    "derau putih keras": lambda: (rng.uniform(-1, 1, (10 * SR, 2))).astype(np.float32),
}


@pytest.mark.parametrize("name", list(SIGNALS))
def test_true_peak_never_above_ceiling(name):
    result = master(SIGNALS[name]())
    assert result.true_peak_dbtp <= CEILING_DBTP
    assert true_peak_db(result.audio) <= CEILING_DBTP


def test_normal_material_reaches_minus_14():
    result = master(music_like(30) * 0.3)
    assert result.integrated_lufs == pytest.approx(-14.0, abs=1.0)
    assert result.integrated_lufs == pytest.approx(-14.0, abs=0.2)
    assert result.target_reached and not result.warnings
    assert result.bus_reduction_db <= 2.0 + 1e-6
    assert result.limiter_reduction_db <= 6.0 + 0.1


def test_very_dynamic_material_warns_and_stays_quieter():
    result = master(_hard_transients(20))
    assert not result.target_reached
    assert result.integrated_lufs < -15.0
    assert result.limiter_reduction_db <= 6.0 + 0.1
    assert any("tidak tercapai" in w and "6 dB" in w for w in result.warnings)


def test_ab_gains_equalize_loudness():
    raw = music_like(20) * 0.2
    mastered = master(raw).audio
    g_raw, g_master = loudness_matched_gains(raw, mastered)
    assert max(g_raw, g_master) == 0.0
    a = integrated_lufs(raw * 10 ** (g_raw / 20))
    b = integrated_lufs(mastered * 10 ** (g_master / 20))
    assert a == pytest.approx(b, abs=0.05)


# ----- ekspor -----

def test_clean_title():
    assert clean_title('Bapa Engkau "Sungguh" Baik?') == "Bapa_Engkau_Sungguh_Baik"
    assert clean_title("Kudus: A/B\\C|D*") == "Kudus_ABCD"
    assert clean_title("  ...  ") == "Lagu"


def test_base_name_never_reuses(tmp_path):
    when = datetime(2026, 11, 6, 14, 30)
    first = base_name("Lagu Saya", tmp_path, when)
    assert first == "Lagu_Saya_20261106-1430"
    (tmp_path / f"{first}_Laporan.txt").write_text("lama")
    assert base_name("Lagu Saya", tmp_path, when) == "Lagu_Saya_20261106-1430-2"


def test_trim_tail_keeps_tail_above_minus_60_and_adds_silence():
    x = np.zeros((5 * SR, 2), np.float32)
    x[:SR] = 0.5
    x[SR:3 * SR] = 0.0005  # -66 dBFS: di bawah -60, boleh dipotong
    x[2 * SR] = 0.002      # -54 dBFS: harus tetap ada
    y = trim_tail(x)
    assert len(y) == 2 * SR + 1 + SR
    assert np.all(y[-SR:] == 0)


def test_tpdf_dither_quantizes_to_24_bit():
    x = np.full((SR, 2), 0.25, dtype=np.float32)
    q = to_pcm24_tpdf(x, seed=1)
    assert np.all(q & 0xFF == 0)
    levels = (q >> 8) - int(0.25 * 2**23)
    assert set(np.unique(levels)) <= {-1, 0, 1}
    assert 0.3 < np.std(levels) < 0.6  # TPDF +-1 LSB: deviasi ~0,41 LSB
    silent = to_pcm24_tpdf(np.zeros((SR, 1), np.float32), seed=2)
    assert np.any(silent != 0)


def test_wav_export_valid_and_never_overwrites(tmp_path):
    path = tmp_path / "m.wav"
    x = music_like(3) * 0.3
    write_wav(path, x, seed=3)
    info = sf.info(str(path))
    assert (info.samplerate, info.channels, info.subtype, info.frames) == (SR, 2, "PCM_24", len(x))
    back, _ = sf.read(str(path), dtype="float32")
    assert np.max(np.abs(back - x)) < 3 / 2**23
    with pytest.raises(FileExistsError):
        write_wav(path, x)


def test_mp3_export_320_cbr_with_title_and_peak(tmp_path):
    wav, mp3 = tmp_path / "m.wav", tmp_path / "m.mp3"
    write_wav(wav, master(music_like(10) * 0.3).audio)
    info = encode_mp3(wav, mp3, "Bapa Engkau Sungguh Baik")
    assert info.true_peak_dbtp <= CEILING_DBTP
    probe = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(mp3)], capture_output=True,
                           text=True, encoding="utf-8", errors="replace").stderr
    assert re.search(r"Audio: mp3.*48000 Hz, stereo.*320 kb/s", probe)
    assert re.search(r"title\s*: Bapa Engkau Sungguh Baik", probe)
    assert abs(len(decode_audio(mp3)) - sf.info(str(wav)).frames) < SR // 10
    with pytest.raises(FileExistsError):
        encode_mp3(wav, mp3, "x")


# ----- produce() -----

@pytest.fixture(scope="module")
def demo_project(tmp_path_factory):
    return create_demo(tmp_path_factory.mktemp("produce"), "Bapa Engkau Sungguh Baik", bars=4)


def test_produce_end_to_end(demo_project):
    steps = []
    result = produce(demo_project, progress=lambda s, p: steps.append((s, p)), verify=True,
                     when=datetime(2026, 11, 6, 9, 5))
    # File & nama
    assert result.wav_path.name == "Bapa_Engkau_Sungguh_Baik_20261106-0905_Master.wav"
    assert result.mp3_path.name == "Bapa_Engkau_Sungguh_Baik_20261106-0905_Master.mp3"
    assert result.report_path.name == "Bapa_Engkau_Sungguh_Baik_20261106-0905_Laporan.txt"
    assert all(p.parent == demo_project.master_dir for p in (result.wav_path, result.mp3_path, result.report_path))
    # Gerbang Sprint 2
    assert result.mastered.true_peak_dbtp <= -1.0
    assert result.mastered.integrated_lufs == pytest.approx(-14.0, abs=1.0)
    assert result.youtube_ready
    assert result.verification.ok
    wav, _ = sf.read(str(result.wav_path), dtype="float32")
    assert true_peak_db(wav) <= -1.0
    assert result.mp3.true_peak_dbtp <= -1.0
    # Ekor reverb utuh: file lebih panjang dari lagu, berakhir 1 detik hening, sebelumnya masih ada ekor.
    song = demo_project.tracks["piano"].active_take.duration
    assert len(wav) / SR > song + 1.0
    assert np.max(np.abs(wav[-SR + 10:])) < 3 / 2**23
    tail = wav[int(song * SR):-SR]
    assert np.max(np.abs(tail)) > 10 ** (-60 / 20)
    # Progres: langkah naik 2..7 (tahap 1 dilewati tanpa DeepFilterNet), persen naik sampai 100.
    numbers = [s for s, _ in steps]
    assert numbers == sorted(numbers) and numbers[0] == 2 and numbers[-1] == 7
    assert [p for _, p in steps] == sorted(p for _, p in steps) and steps[-1][1] == 100
    # Laporan
    text = result.report_path.read_text(encoding="utf-8")
    for word in ("Kelantangan", "True Peak", "LRA", "Durasi", "Reduksi limiter", "Katedral · Normal",
                 "Siap YouTube", "DeepFilterNet"):
        assert word in text
    # A/B
    g_raw, g_master = result.ab_gains_db
    assert integrated_lufs(result.raw * 10 ** (g_raw / 20)) == pytest.approx(
        integrated_lufs(result.mastered.audio * 10 ** (g_master / 20)), abs=0.15)


def test_produce_twice_never_overwrites(demo_project):
    when = datetime(2026, 11, 6, 10, 0)
    a = produce(demo_project, when=when)
    b = produce(demo_project, when=when)
    assert a.wav_path != b.wav_path and b.wav_path.name.endswith("-2_Master.wav")
    assert a.wav_path.exists() and b.wav_path.exists()


def test_produce_step_one_with_denoiser(demo_project):
    steps = []
    produce(demo_project, progress=lambda s, p: steps.append(s), export=False, denoiser=lambda x: x)
    assert steps[0] == 1
    assert set(steps) == set(STEP_LABELS)


def test_produce_cancel(demo_project):
    flag = threading.Event()

    def progress(step, pct):
        if step >= 7:
            flag.set()

    before = set(demo_project.master_dir.iterdir())
    with pytest.raises(ProcessingCancelled):
        produce(demo_project, progress=progress, cancel=flag)
    assert set(demo_project.master_dir.iterdir()) == before
