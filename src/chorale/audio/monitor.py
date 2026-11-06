"""Meter input live (dipakai layar Pengaturan): hanya membaca input, tidak merekam."""

from __future__ import annotations

import numpy as np

from chorale.audio.device import (
    DEFAULT_BLOCKSIZE, HOSTAPI_WASAPI, SAMPLE_RATE, AudioDeviceError, DeviceSelection, friendly_error,
)
from chorale.audio.meter import LevelMeter

import sounddevice as sd  # noqa: E402  (device sudah meng-import lebih dulu)


class InputMonitor:
    """Buka input sound card dan simpan puncak per kanal untuk dibaca UI."""

    def __init__(self, selection: DeviceSelection, blocksize: int = DEFAULT_BLOCKSIZE):
        self.selection = selection
        self.meter = LevelMeter(selection.input_channels)
        self._blocksize = blocksize
        self._stream: sd.InputStream | None = None

    def _callback(self, indata, frames, time_info, status):
        self.meter.update(indata)

    def start(self) -> None:
        extra = None
        if self.selection.hostapi == HOSTAPI_WASAPI:
            extra = sd.WasapiSettings(exclusive=self.selection.exclusive)
        try:
            self._stream = sd.InputStream(
                device=self.selection.input.index, channels=self.selection.input_channels,
                samplerate=SAMPLE_RATE, dtype="float32", latency="low", blocksize=self._blocksize,
                extra_settings=extra, callback=self._callback)
            self._stream.start()
        except Exception as exc:  # noqa: BLE001
            self._stream = None
            raise AudioDeviceError(friendly_error(exc), technical=str(exc)) from exc

    def peaks_db(self) -> np.ndarray:
        from chorale.audio.meter import to_dbfs
        return to_dbfs(self.meter.read())

    @property
    def active(self) -> bool:
        return self._stream is not None and self._stream.active

    def stop(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:  # noqa: BLE001 - perangkat mungkin sudah dicabut
                pass
            self._stream = None
