"""Tes perekam dengan input palsu (tanpa hardware)."""

import shutil
import struct
import threading
import time

import numpy as np
import pytest
import soundfile as sf

from chorale.audio.recorder import Recorder, RingBuffer, check_free_space

SR = 48000
BLOCK = 256
LSB_24 = 1 / 2**23


def _signal(frames, channels, seed=0):
    rng = np.random.default_rng(seed)
    return (0.5 * rng.uniform(-1, 1, (frames, channels))).astype(np.float32)


def _feed(recorder, data, realtime=False):
    """Kirim data per blok seperti callback audio, dari thread lain."""
    def run():
        for i in range(0, len(data), BLOCK):
            recorder.process_input(data[i:i + BLOCK])
            if realtime:
                time.sleep(BLOCK / SR)
    t = threading.Thread(target=run)
    t.start()
    t.join()


def test_ring_buffer_wraparound():
    ring = RingBuffer(10, 1)
    out = []
    for start in range(0, 40, 7):
        ring.write(np.arange(start, start + 7, dtype=np.float32)[:, None])
        out.append(ring.read())
    assert np.array_equal(np.concatenate(out)[:, 0], np.arange(42))
    assert ring.overrun_frames == 0


def test_ring_buffer_overrun_counted():
    ring = RingBuffer(10, 1)
    ring.write(np.ones((25, 1), dtype=np.float32))
    assert ring.overrun_frames == 15
    assert len(ring.read()) == 10


@pytest.mark.parametrize("channels,first", [(1, 0), (2, 0), (1, 1)])
def test_recorded_wav_valid_and_exact(tmp_path, channels, first):
    stream_in = _signal(3 * SR + 100, 2)  # sound card 2 kanal; panjang bukan kelipatan blok
    path = tmp_path / "take.wav"
    rec = Recorder(path, channels, first_channel=first)
    rec.start()
    _feed(rec, stream_in)
    result = rec.stop()

    info = sf.info(str(path))
    assert (info.samplerate, info.channels, info.subtype, info.format) == (SR, channels, "PCM_24", "WAV")
    assert info.frames == len(stream_in) == result.frames
    assert result.overrun_frames == 0 and result.error is None
    audio, _ = sf.read(str(path), dtype="float32", always_2d=True)
    assert np.max(np.abs(audio - stream_in[:, first:first + channels])) <= LSB_24


def test_values_above_full_scale_are_clipped(tmp_path):
    path = tmp_path / "clip.wav"
    rec = Recorder(path, 1)
    rec.start()
    _feed(rec, np.full((1024, 1), 1.7, dtype=np.float32))
    rec.stop()
    audio, _ = sf.read(str(path), dtype="float32")
    assert np.all(audio > 0.99) and np.all(audio <= 1.0)


def test_never_overwrites_existing_file(tmp_path):
    path = tmp_path / "ada.wav"
    path.write_bytes(b"lama")
    with pytest.raises(FileExistsError):
        Recorder(path, 1).start()
    assert path.read_bytes() == b"lama"


def test_file_readable_mid_recording_like_power_loss(tmp_path):
    """Salinan file saat masih merekam (= kondisi listrik padam) harus valid dan hampir lengkap."""
    path = tmp_path / "live.wav"
    rec = Recorder(path, 1, flush_interval=0.2)
    rec.start()
    data = _signal(SR, 1)
    _feed(rec, data)
    time.sleep(0.5)  # beri waktu thread penulis menulis + memperbarui header
    snapshot = tmp_path / "snapshot.wav"
    shutil.copyfile(path, snapshot)
    _feed(rec, _signal(SR // 2, 1, seed=1))
    rec.stop()

    # Header harus mencatat ukuran data yang benar; libsndfile memaafkan header 0,
    # tetapi FFmpeg/DAW lain bisa menganggap file kosong.
    raw = snapshot.read_bytes()
    i = raw.find(b"data")
    assert struct.unpack("<I", raw[i + 4:i + 8])[0] == SR * 3
    info = sf.info(str(snapshot))
    assert info.frames == SR
    audio, _ = sf.read(str(snapshot), dtype="float32", always_2d=True)
    assert np.max(np.abs(audio - data)) <= LSB_24
    assert sf.info(str(path)).frames == SR + SR // 2


def test_stop_when_input_ends_abruptly(tmp_path):
    """Perangkat dicabut = input berhenti tiba-tiba; file tetap valid sampai data terakhir."""
    path = tmp_path / "putus.wav"
    rec = Recorder(path, 2)
    rec.start()
    _feed(rec, _signal(12345, 2), realtime=True)
    result = rec.stop()
    assert sf.info(str(path)).frames == 12345 == result.frames


def test_disk_space_warning(tmp_path):
    assert check_free_space(tmp_path).ok
    low = check_free_space(tmp_path / "belum" / "ada", minimum=10**18)
    assert not low.ok and "2 GB" in low.message
