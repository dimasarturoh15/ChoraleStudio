"""Metronom sintetis yang tepat per sampel (PRD FR-4).

Garis waktu lagu: frame 0 = awal birama pertama setelah count-in. Ketukan ke-k
jatuh tepat di frame round(k * sampel_per_ketukan). Ketukan count-in memakai k
negatif. Posisi tiap ketukan dihitung langsung dari k (bukan dijumlahkan), jadi
tidak ada pergeseran meski tempo menghasilkan pecahan sampel.

Untuk 6/8, tempo dihitung per seperdelapan (6 klik per birama).
"""

from __future__ import annotations

import math

import numpy as np

from chorale.project.model import TIME_SIGNATURES

SAMPLE_RATE = 48000
BEATS_PER_BAR = {"2/4": 2, "3/4": 3, "4/4": 4, "6/8": 6}
ACCENT_FREQ = 1760.0
BEAT_FREQ = 880.0
CLICK_SECONDS = 0.03
DEFAULT_VOLUME_DB = -6.0

assert set(BEATS_PER_BAR) == set(TIME_SIGNATURES)


def make_click(freq: float, samplerate: int = SAMPLE_RATE, duration: float = CLICK_SECONDS) -> np.ndarray:
    """Satu bunyi klik: sinus dengan serangan 1 ms dan peluruhan cepat, puncak ~1.0."""
    t = np.arange(int(duration * samplerate)) / samplerate
    env = np.minimum(t / 0.001, 1.0) * np.exp(-t / (duration / 5))
    return (np.sin(2 * np.pi * freq * t) * env).astype(np.float32)


class Metronome:
    """Hasilkan klik ke buffer output untuk rentang frame mana pun pada garis waktu lagu."""

    def __init__(self, tempo: int, time_signature: str, count_in_bars: int = 0,
                 click_during_song: bool = True, volume_db: float = DEFAULT_VOLUME_DB,
                 samplerate: int = SAMPLE_RATE):
        if time_signature not in BEATS_PER_BAR:
            raise ValueError(f"Birama tidak dikenal: {time_signature}")
        self.samples_per_beat = 60.0 * samplerate / tempo
        self.beats_per_bar = BEATS_PER_BAR[time_signature]
        self.count_in_beats = count_in_bars * self.beats_per_bar
        self.count_in_frames = self.beat_frame(0) - self.beat_frame(-self.count_in_beats)
        self.click_during_song = click_during_song
        gain = 10 ** (volume_db / 20)
        self._accent = make_click(ACCENT_FREQ, samplerate) * gain
        self._beat = make_click(BEAT_FREQ, samplerate) * gain
        self._click_len = len(self._accent)

    @classmethod
    def for_project(cls, project, click_during_song: bool | None = None,
                    volume_db: float = DEFAULT_VOLUME_DB) -> "Metronome":
        if click_during_song is None:
            click_during_song = project.metronome_after_count_in
        return cls(project.tempo, project.time_signature, project.count_in_bars,
                   click_during_song, volume_db)

    def beat_frame(self, k: int) -> int:
        """Frame (garis waktu lagu) tempat ketukan ke-k berbunyi."""
        return round(k * self.samples_per_beat)

    def is_accent(self, k: int) -> bool:
        return k % self.beats_per_bar == 0

    def _audible(self, k: int) -> bool:
        if k < 0:
            return k >= -self.count_in_beats
        return self.click_during_song

    def render(self, out: np.ndarray, song_start: int) -> None:
        """Tambahkan klik ke `out` (frames, kanal) yang mewakili frame [song_start, song_start+len).

        Aman dipanggil dari callback audio: hanya slicing dan penjumlahan di tempat.
        """
        n = len(out)
        k = math.floor((song_start - self._click_len) / self.samples_per_beat)
        end = song_start + n
        while True:
            pos = self.beat_frame(k)
            if pos >= end:
                break
            if self._audible(k):
                a = pos - song_start
                lo, hi = max(0, a), min(n, a + self._click_len)
                if lo < hi:
                    click = self._accent if self.is_accent(k) else self._beat
                    out[lo:hi] += click[lo - a:hi - a, None]
            elif k >= 0:
                break
            k += 1

    def click_train(self, frames: int, song_start: int = 0) -> np.ndarray:
        """Render klik mono untuk analisis (misalnya uji sinkron)."""
        out = np.zeros((frames, 1), dtype=np.float32)
        self.render(out, song_start)
        return out[:, 0]
