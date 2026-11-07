"""Model proyek: satu proyek = satu lagu = satu folder (PRD FR-2, FR-9).

Setiap perubahan lewat metode Project otomatis disimpan ke proyek.json
(jika proyek sudah punya folder).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from chorale.appdirs import write_json_atomic

PROJECT_FILE = "proyek.json"
TAKES_DIR = "takes"
MASTER_DIR = "master"
SCHEMA_VERSION = 1

TRACK_IDS = ("piano", "bass", "tenor", "alto", "sopran")
VOCAL_TRACK_IDS = TRACK_IDS[1:]
TRACK_LABELS = {
    "piano": "Piano/Orgen",
    "bass": "Bass",
    "tenor": "Tenor",
    "alto": "Alto",
    "sopran": "Sopran",
}
TRACK_CHANNELS = {"piano": 2, "bass": 1, "tenor": 1, "alto": 1, "sopran": 1}

TEMPO_MIN, TEMPO_MAX = 40, 240
TIME_SIGNATURES = ("2/4", "3/4", "4/4", "6/8")
COUNT_IN_CHOICES = (0, 1, 2)
VOLUME_MIN_DB, VOLUME_MAX_DB = -12.0, 6.0

ROOM_PRESET_IDS = ("gereja_kecil", "aula", "katedral")
REVERB_AMOUNT_IDS = ("sedikit", "normal", "banyak")
DEFAULT_ROOM = "katedral"
DEFAULT_REVERB_AMOUNT = "normal"

TAKE_FILE_RE = re.compile(r"^(?P<track>[a-z]+)_take(?P<number>\d+)_(?P<stamp>\d{8}-\d{6})\.wav$")
STAMP_FORMAT = "%Y%m%d-%H%M%S"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class Take:
    """Satu rekaman dari satu track. complete=False jika rekaman terhenti tidak normal."""

    id: int
    filename: str
    recorded_at: str
    duration: float
    complete: bool = True
    latency_compensation: int = 0  # sampel yang dibuang di awal agar sejajar dengan track lain
    alignment: str = "kalibrasi"   # "kalibrasi" atau "acuan" (disejajarkan memakai kanal acuan)

    @property
    def label(self) -> str:
        """Teks untuk daftar take, contoh 'Take 2 · 13:01'."""
        try:
            hhmm = datetime.fromisoformat(self.recorded_at).strftime("%H:%M")
        except ValueError:
            hhmm = "--:--"
        return f"Take {self.id} · {hhmm}"


@dataclass
class Track:
    """Satu dari 5 track tetap."""

    id: str
    takes: list[Take] = field(default_factory=list)
    active_take_id: int | None = None
    volume_db: float = 0.0
    solo: bool = False
    mute: bool = False
    denoise: bool = True  # peredam derau (hanya berlaku untuk track vokal)

    @property
    def label(self) -> str:
        return TRACK_LABELS[self.id]

    @property
    def channels(self) -> int:
        return TRACK_CHANNELS[self.id]

    @property
    def active_take(self) -> Take | None:
        return next((t for t in self.takes if t.id == self.active_take_id), None)

    @property
    def has_audio(self) -> bool:
        return self.active_take is not None

    def get_take(self, take_id: int) -> Take:
        for take in self.takes:
            if take.id == take_id:
                return take
        raise KeyError(f"Take {take_id} tidak ada di track {self.label}")

    @classmethod
    def from_dict(cls, data: dict) -> "Track":
        takes = [Take(**t) for t in data.get("takes", [])]
        return cls(
            id=data["id"],
            takes=takes,
            active_take_id=data.get("active_take_id"),
            volume_db=float(data.get("volume_db", 0.0)),
            solo=bool(data.get("solo", False)),
            mute=bool(data.get("mute", False)),
            denoise=bool(data.get("denoise", True)),
        )


def validate_settings(tempo=None, time_signature=None, count_in_bars=None, title=None,
                      room_preset=None, reverb_amount=None) -> None:
    """Lempar ValueError berbahasa Indonesia jika pengaturan lagu tidak valid."""
    if title is not None and not str(title).strip():
        raise ValueError("Judul lagu tidak boleh kosong.")
    if tempo is not None and not (TEMPO_MIN <= int(tempo) <= TEMPO_MAX):
        raise ValueError(f"Tempo harus antara {TEMPO_MIN} dan {TEMPO_MAX} BPM.")
    if time_signature is not None and time_signature not in TIME_SIGNATURES:
        raise ValueError(f"Birama harus salah satu dari: {', '.join(TIME_SIGNATURES)}.")
    if count_in_bars is not None and count_in_bars not in COUNT_IN_CHOICES:
        raise ValueError("Hitungan awal harus 0, 1, atau 2 bar.")
    if room_preset is not None and room_preset not in ROOM_PRESET_IDS:
        raise ValueError(f"Preset ruang tidak dikenal: {room_preset}")
    if reverb_amount is not None and reverb_amount not in REVERB_AMOUNT_IDS:
        raise ValueError(f"Jumlah reverb tidak dikenal: {reverb_amount}")


@dataclass
class Project:
    """Satu lagu beserta 5 track-nya."""

    title: str
    tempo: int = 72
    time_signature: str = "4/4"
    count_in_bars: int = 2
    metronome_after_count_in: bool = True
    room_preset: str = DEFAULT_ROOM
    reverb_amount: str = DEFAULT_REVERB_AMOUNT
    vocal_guide_done: bool = False
    created_at: str = field(default_factory=now_iso)
    modified_at: str = field(default_factory=now_iso)
    tracks: dict[str, Track] = field(default_factory=lambda: {t: Track(t) for t in TRACK_IDS})
    folder: Path | None = field(default=None, repr=False, compare=False)
    autosave: bool = field(default=True, repr=False, compare=False)

    def __post_init__(self):
        validate_settings(self.tempo, self.time_signature, self.count_in_bars, self.title,
                          self.room_preset, self.reverb_amount)

    # ----- lokasi file -----
    @property
    def project_file(self) -> Path:
        return self._require_folder() / PROJECT_FILE

    @property
    def takes_dir(self) -> Path:
        return self._require_folder() / TAKES_DIR

    @property
    def master_dir(self) -> Path:
        return self._require_folder() / MASTER_DIR

    def take_path(self, take: Take) -> Path:
        return self.takes_dir / take.filename

    def _require_folder(self) -> Path:
        if self.folder is None:
            raise RuntimeError("Proyek belum punya folder.")
        return self.folder

    # ----- simpan -----
    def to_dict(self) -> dict:
        return {
            "version": SCHEMA_VERSION,
            "title": self.title,
            "tempo": self.tempo,
            "time_signature": self.time_signature,
            "count_in_bars": self.count_in_bars,
            "metronome_after_count_in": self.metronome_after_count_in,
            "room_preset": self.room_preset,
            "reverb_amount": self.reverb_amount,
            "vocal_guide_done": self.vocal_guide_done,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "tracks": [
                {
                    "id": tr.id,
                    "active_take_id": tr.active_take_id,
                    "volume_db": tr.volume_db,
                    "solo": tr.solo,
                    "mute": tr.mute,
                    "denoise": tr.denoise,
                    "takes": [asdict(t) for t in tr.takes],
                }
                for tr in self.tracks.values()
            ],
        }

    @classmethod
    def from_dict(cls, data: dict, folder: Path | None = None) -> "Project":
        tracks = {t: Track(t) for t in TRACK_IDS}
        for td in data.get("tracks", []):
            if td.get("id") in tracks:
                tracks[td["id"]] = Track.from_dict(td)
        return cls(
            title=data["title"],
            tempo=int(data.get("tempo", 72)),
            time_signature=data.get("time_signature", "4/4"),
            count_in_bars=int(data.get("count_in_bars", 2)),
            metronome_after_count_in=bool(data.get("metronome_after_count_in", True)),
            room_preset=data.get("room_preset", DEFAULT_ROOM),
            reverb_amount=data.get("reverb_amount", DEFAULT_REVERB_AMOUNT),
            vocal_guide_done=bool(data.get("vocal_guide_done", False)),
            created_at=data.get("created_at", now_iso()),
            modified_at=data.get("modified_at", now_iso()),
            tracks=tracks,
            folder=folder,
        )

    def save(self) -> None:
        """Simpan proyek.json secara atomik (file sementara lalu ganti nama)."""
        write_json_atomic(self.project_file, self.to_dict())

    def _changed(self) -> None:
        self.modified_at = now_iso()
        if self.folder is not None and self.autosave:
            self.save()

    # ----- ubah pengaturan -----
    def update_settings(self, **changes) -> None:
        """Ubah judul/tempo/birama/hitungan awal/metronom/preset ruang/jumlah reverb."""
        allowed = {"title", "tempo", "time_signature", "count_in_bars", "metronome_after_count_in",
                   "room_preset", "reverb_amount", "vocal_guide_done"}
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f"Pengaturan tidak dikenal: {', '.join(sorted(unknown))}")
        validate_settings(changes.get("tempo"), changes.get("time_signature"),
                          changes.get("count_in_bars"), changes.get("title"),
                          changes.get("room_preset"), changes.get("reverb_amount"))
        for key, value in changes.items():
            setattr(self, key, value)
        self._changed()

    def track(self, track_id: str) -> Track:
        if track_id not in self.tracks:
            raise KeyError(f"Track tidak dikenal: {track_id}")
        return self.tracks[track_id]

    def set_volume(self, track_id: str, volume_db: float) -> None:
        volume_db = float(volume_db)
        if not (VOLUME_MIN_DB <= volume_db <= VOLUME_MAX_DB):
            raise ValueError(f"Volume harus antara {VOLUME_MIN_DB:g} dan +{VOLUME_MAX_DB:g} dB.")
        self.track(track_id).volume_db = volume_db
        self._changed()

    def set_solo(self, track_id: str, solo: bool) -> None:
        self.track(track_id).solo = bool(solo)
        self._changed()

    def set_mute(self, track_id: str, mute: bool) -> None:
        self.track(track_id).mute = bool(mute)
        self._changed()

    def set_denoise(self, track_id: str, enabled: bool) -> None:
        self.track(track_id).denoise = bool(enabled)
        self._changed()

    def set_active_take(self, track_id: str, take_id: int) -> None:
        track = self.track(track_id)
        track.get_take(take_id)
        track.active_take_id = take_id
        self._changed()

    # ----- take -----
    def can_record(self, track_id: str) -> tuple[bool, str]:
        """Track vokal baru boleh direkam setelah track Piano punya rekaman (FR-2)."""
        self.track(track_id)
        if track_id in VOCAL_TRACK_IDS and not self.tracks["piano"].has_audio:
            return False, "Rekam Piano/Orgen dulu. Piano adalah panduan wajib untuk semua suara."
        return True, ""

    def next_take_path(self, track_id: str, when: datetime | None = None) -> tuple[int, Path]:
        """Nomor take berikutnya dan path file baru yang belum pernah ada."""
        track = self.track(track_id)
        when = when or datetime.now()
        used = {t.id for t in track.takes}
        if self.takes_dir.is_dir():
            for f in self.takes_dir.iterdir():
                m = TAKE_FILE_RE.match(f.name)
                if m and m["track"] == track_id:
                    used.add(int(m["number"]))
        number = max(used, default=0) + 1
        stamp = when.strftime(STAMP_FORMAT)
        while True:
            path = self.takes_dir / f"{track_id}_take{number}_{stamp}.wav"
            if not path.exists():
                return number, path
            number += 1

    def add_take(self, track_id: str, take: Take, make_active: bool = True) -> None:
        """Daftarkan take baru (take lama tidak pernah dihapus)."""
        track = self.track(track_id)
        if any(t.id == take.id for t in track.takes):
            raise ValueError(f"Take {take.id} sudah ada di track {track.label}")
        track.takes.append(take)
        if make_active or track.active_take_id is None:
            track.active_take_id = take.id
        self._changed()
