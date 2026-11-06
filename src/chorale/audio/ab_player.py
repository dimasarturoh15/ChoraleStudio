"""Pemutar A/B (PRD FR-9): Mentah vs Master dengan kelantangan disamakan.

Kedua versi disiapkan sekali (sudah diberi gain penyama kelantangan dan
panjang yang sama). Callback hanya menyalin dari buffer yang sedang dipilih,
jadi berpindah A/B tidak memutus posisi putar.
"""

from __future__ import annotations

import time

import numpy as np

from chorale.audio.device import (
    DEFAULT_BLOCKSIZE, HOSTAPI_WASAPI, SAMPLE_RATE, AudioDeviceError, DeviceSelection, friendly_error,
)

import sounddevice as sd  # noqa: E402  (device sudah meng-import lebih dulu)

SOURCE_A, SOURCE_B = 0, 1


def _prepare(audio: np.ndarray, gain_db: float, length: int) -> np.ndarray:
    audio = audio if audio.ndim == 2 else audio[:, None]
    stereo = audio[:, :2] if audio.shape[1] >= 2 else np.repeat(audio[:, :1], 2, axis=1)
    out = np.zeros((length, 2), dtype=np.float32)
    out[:len(stereo)] = stereo * np.float32(10 ** (gain_db / 20))
    return out


def open_output_stream(selection: DeviceSelection, callback, blocksize: int):
    extra = sd.WasapiSettings(exclusive=selection.exclusive) if selection.hostapi == HOSTAPI_WASAPI else None
    try:
        return sd.OutputStream(device=selection.output.index, channels=2, samplerate=SAMPLE_RATE,
                               dtype="float32", latency="low", blocksize=blocksize, extra_settings=extra,
                               callback=callback)
    except Exception as exc:  # noqa: BLE001
        raise AudioDeviceError(friendly_error(exc), technical=str(exc)) from exc


class ABPlayer:
    def __init__(self, selection: DeviceSelection | None, raw: np.ndarray, master: np.ndarray,
                 gain_a_db: float = 0.0, gain_b_db: float = 0.0, blocksize: int = DEFAULT_BLOCKSIZE,
                 stream_factory=open_output_stream, device_timeout: float = 1.0):
        self.selection = selection
        length = max(len(raw), len(master))
        self._buffers = (_prepare(raw, gain_a_db, length), _prepare(master, gain_b_db, length))
        self._length = length
        self.source = SOURCE_B
        self._pos = 0
        self._blocksize = blocksize
        self._factory = stream_factory
        self._stream = None
        self._last_callback = 0.0
        self.device_timeout = device_timeout

    # ----- callback -----
    def _callback(self, outdata, frames, time_info, status):
        self._last_callback = time.monotonic()
        start = self._pos
        n = max(0, min(frames, self._length - start))
        if n:
            outdata[:n] = self._buffers[self.source][start:start + n]
        outdata[n:] = 0.0
        self._pos = start + frames

    # ----- kendali -----
    @property
    def playing(self) -> bool:
        return self._stream is not None

    @property
    def length_seconds(self) -> float:
        return self._length / SAMPLE_RATE

    @property
    def position_seconds(self) -> float:
        return min(self._pos, self._length) / SAMPLE_RATE

    @property
    def ended(self) -> bool:
        return self._pos >= self._length

    @property
    def device_lost(self) -> bool:
        return self._stream is not None and time.monotonic() - self._last_callback > self.device_timeout

    def set_source(self, source: int) -> None:
        self.source = SOURCE_A if source == SOURCE_A else SOURCE_B

    def seek(self, seconds: float) -> None:
        self._pos = int(max(0.0, min(seconds, self.length_seconds)) * SAMPLE_RATE)

    def play(self) -> None:
        if self._stream is not None:
            return
        if self.selection is None:
            raise AudioDeviceError("Sound card tidak ditemukan.")
        if self.ended:
            self._pos = 0
        self._stream = self._factory(self.selection, self._callback, self._blocksize)
        self._last_callback = time.monotonic()
        try:
            self._stream.start()
        except Exception as exc:  # noqa: BLE001
            self._stream = None
            raise AudioDeviceError(friendly_error(exc), technical=str(exc)) from exc

    def pause(self) -> None:
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:  # noqa: BLE001 - perangkat mungkin sudah dicabut
                pass

    def close(self) -> None:
        self.pause()
