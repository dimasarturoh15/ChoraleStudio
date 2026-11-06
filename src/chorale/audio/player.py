"""Mixer monitoring dan pemutar.

Campuran stereo dibuat SEBELUM stream dimulai; callback hanya menyalin
potongan dari buffer itu (tanpa mixing di callback).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from chorale.project.model import Project


def db_to_gain(db: float) -> float:
    return float(10.0 ** (db / 20.0))


@dataclass
class TrackAudio:
    """Audio satu track beserta pengaturan mixer-nya."""

    track_id: str
    audio: np.ndarray  # (frames, kanal) float32, mono atau stereo
    volume_db: float = 0.0
    solo: bool = False
    mute: bool = False


def audible_tracks(tracks: list[TrackAudio], exclude: str | None = None) -> list[TrackAudio]:
    """Track yang terdengar: jika ada solo hanya yang di-solo; mute selalu menang.

    Track `exclude` (yang sedang direkam) tidak pernah ikut, agar suara penyanyi
    maupun take lamanya tidak diputar ulang (FR-3).
    """
    candidates = [t for t in tracks if t.track_id != exclude]
    if any(t.solo for t in candidates):
        candidates = [t for t in candidates if t.solo]
    return [t for t in candidates if not t.mute]


def mix_tracks(tracks: list[TrackAudio], exclude: str | None = None, gain_db: float = 0.0) -> np.ndarray:
    """Campur track menjadi buffer stereo float32. Mono diletakkan di tengah."""
    play = audible_tracks(tracks, exclude)
    length = max((len(t.audio) for t in play), default=0)
    mix = np.zeros((length, 2), dtype=np.float32)
    for t in play:
        audio = t.audio if t.audio.ndim == 2 else t.audio[:, None]
        g = db_to_gain(t.volume_db + gain_db)
        n = len(audio)
        if audio.shape[1] == 1:
            mix[:n] += audio[:, :1] * g
        else:
            mix[:n] += audio[:, :2] * g
    return mix


def load_take_audio(path: Path) -> np.ndarray:
    audio, _ = sf.read(str(path), dtype="float32", always_2d=True)
    return audio


def project_track_audio(project: Project) -> list[TrackAudio]:
    """Muat take aktif dari semua track yang punya rekaman."""
    result = []
    for track in project.tracks.values():
        take = track.active_take
        if take is None:
            continue
        path = project.take_path(take)
        if not path.is_file():
            continue
        result.append(TrackAudio(track.id, load_take_audio(path), track.volume_db, track.solo, track.mute))
    return result


def build_monitor_mix(project: Project, exclude: str | None = None, gain_db: float = 0.0) -> np.ndarray:
    return mix_tracks(project_track_audio(project), exclude=exclude, gain_db=gain_db)


class Player:
    """Putar buffer yang sudah dimix; setelah habis mengeluarkan hening."""

    def __init__(self, mix: np.ndarray, samplerate: int = 48000):
        self._mix = np.ascontiguousarray(mix, dtype=np.float32)
        self._samplerate = samplerate
        self._pos = 0

    @property
    def length_frames(self) -> int:
        return len(self._mix)

    @property
    def position_frames(self) -> int:
        return self._pos

    @property
    def position_seconds(self) -> float:
        return self._pos / self._samplerate

    @property
    def finished(self) -> bool:
        return self._pos >= len(self._mix)

    def seek(self, frame: int = 0) -> None:
        """Pindah ke frame lagu; nilai negatif berarti masih dalam count-in."""
        self._pos = int(frame)

    def process_output(self, outdata: np.ndarray) -> None:
        """Dipanggil dari callback audio: salin potongan buffer ke output.

        Posisi boleh negatif (selama count-in): bagian sebelum frame 0 diisi hening.
        """
        frames = len(outdata)
        start = self._pos
        skip = min(frames, max(0, -start))
        src = max(0, start)
        n = max(0, min(frames - skip, len(self._mix) - src))
        outdata.fill(0.0)
        if n:
            if outdata.shape[1] == 2:
                outdata[skip:skip + n] = self._mix[src:src + n]
            else:
                outdata[skip:skip + n, 0] = self._mix[src:src + n, 0]
        self._pos = start + frames
