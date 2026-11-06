"""Tes model proyek: simpan/buka, take baru tidak menimpa, take aktif, daftar terakhir."""

import json
from datetime import datetime

import numpy as np
import pytest
import soundfile as sf

from chorale.project import Project, Take, add_recent, create_project, list_recent, open_project
from chorale.project.store import safe_folder_name

WHEN = datetime(2026, 11, 6, 14, 30, 5)


def _take(project, track_id, when=WHEN, seconds=1.0):
    number, path = project.next_take_path(track_id, when)
    sf.write(str(path), np.zeros((int(48000 * seconds), project.track(track_id).channels)),
             48000, subtype="PCM_24")
    take = Take(number, path.name, when.isoformat(timespec="seconds"), seconds)
    project.add_take(track_id, take)
    return take


def test_create_makes_folder_structure(tmp_path):
    p = create_project(tmp_path, "Bapa Engkau Sungguh Baik", tempo=72)
    assert (p.folder / "proyek.json").is_file()
    assert (p.folder / "takes").is_dir()
    assert (p.folder / "master").is_dir()
    assert [t for t in p.tracks] == ["piano", "bass", "tenor", "alto", "sopran"]
    assert p.tracks["piano"].channels == 2 and p.tracks["bass"].channels == 1


def test_create_never_reuses_existing_folder(tmp_path):
    a = create_project(tmp_path, "Lagu")
    b = create_project(tmp_path, "Lagu")
    assert a.folder != b.folder
    assert b.folder.name == "Lagu (2)"


def test_safe_folder_name():
    assert safe_folder_name('Kudus: "Agung"?') == "Kudus_ _Agung__"
    assert safe_folder_name("  ...  ") == "Proyek"


def test_roundtrip_save_open(tmp_path):
    p = create_project(tmp_path, "Lagu", tempo=90, time_signature="3/4", count_in_bars=1)
    _take(p, "piano")
    p.set_volume("piano", -3.5)
    p.set_solo("bass", True)
    p.set_mute("alto", True)
    p.update_settings(metronome_after_count_in=False)

    q = open_project(p.folder)
    assert q == p
    assert q.tracks["piano"].active_take.filename == p.tracks["piano"].active_take.filename
    assert q.tracks["piano"].volume_db == -3.5
    assert q.metronome_after_count_in is False


def test_every_change_is_autosaved_atomically(tmp_path):
    p = create_project(tmp_path, "Lagu")
    p.update_settings(tempo=120)
    data = json.loads((p.folder / "proyek.json").read_text(encoding="utf-8"))
    assert data["tempo"] == 120
    assert not list(p.folder.glob("*.tmp"))


@pytest.mark.parametrize("kwargs", [
    {"tempo": 39}, {"tempo": 241}, {"time_signature": "5/4"}, {"count_in_bars": 3}, {"title": "  "},
])
def test_invalid_settings_rejected(tmp_path, kwargs):
    p = create_project(tmp_path, "Lagu")
    with pytest.raises(ValueError):
        p.update_settings(**kwargs)


def test_volume_range(tmp_path):
    p = create_project(tmp_path, "Lagu")
    p.set_volume("bass", -12)
    p.set_volume("bass", 6)
    with pytest.raises(ValueError):
        p.set_volume("bass", 6.5)
    with pytest.raises(ValueError):
        p.set_volume("bass", -12.5)


def test_take_filename_format_and_numbering(tmp_path):
    p = create_project(tmp_path, "Lagu")
    t1 = _take(p, "piano")
    t2 = _take(p, "piano", datetime(2026, 11, 6, 14, 31, 0))
    assert t1.filename == "piano_take1_20261106-143005.wav"
    assert t2.filename == "piano_take2_20261106-143100.wav"
    assert p.tracks["piano"].active_take_id == 2
    assert len(p.tracks["piano"].takes) == 2


def test_new_take_never_overwrites_existing_file(tmp_path):
    p = create_project(tmp_path, "Lagu")
    # File asing dengan nomor yang akan dipakai berikutnya sudah ada di disk.
    stray = p.takes_dir / "bass_take1_20261106-143005.wav"
    stray.write_bytes(b"jangan ditimpa")
    number, path = p.next_take_path("bass", WHEN)
    assert number == 2
    assert path != stray and not path.exists()
    assert stray.read_bytes() == b"jangan ditimpa"


def test_active_take_selection(tmp_path):
    p = create_project(tmp_path, "Lagu")
    _take(p, "piano")
    _take(p, "piano", datetime(2026, 11, 6, 15, 0, 0))
    p.set_active_take("piano", 1)
    assert open_project(p.folder).tracks["piano"].active_take_id == 1
    with pytest.raises(KeyError):
        p.set_active_take("piano", 99)


def test_vocal_requires_piano(tmp_path):
    p = create_project(tmp_path, "Lagu")
    ok, reason = p.can_record("bass")
    assert not ok and "Piano" in reason
    assert p.can_record("piano") == (True, "")
    _take(p, "piano")
    assert p.can_record("sopran") == (True, "")


def test_take_label():
    assert Take(2, "x.wav", "2026-11-06T13:01:44", 3.0).label == "Take 2 · 13:01"


def test_orphan_take_recovered_as_incomplete(tmp_path):
    p = create_project(tmp_path, "Lagu")
    _take(p, "piano")
    # Simulasi listrik padam: file take tertulis, tetapi proyek.json belum mencatatnya.
    orphan = p.takes_dir / "tenor_take1_20261106-150000.wav"
    sf.write(str(orphan), np.zeros((24000, 1)), 48000, subtype="PCM_24")

    q = open_project(p.folder)
    tenor = q.tracks["tenor"]
    assert len(tenor.takes) == 1
    assert tenor.takes[0].complete is False
    assert tenor.takes[0].duration == pytest.approx(0.5)
    assert tenor.active_take_id is None
    assert "tenor_take1" in (p.folder / "proyek.json").read_text(encoding="utf-8")


def test_recent_list(tmp_path):
    recent = tmp_path / "cfg" / "recent.json"
    projects = [create_project(tmp_path, f"Lagu {i}") for i in range(12)]
    for p in projects:
        add_recent(p, recent)
    add_recent(projects[3], recent)
    entries = list_recent(recent)
    assert len(entries) == 10
    assert entries[0]["title"] == "Lagu 3"
    assert len({e["path"] for e in entries}) == 10


def test_recent_skips_deleted_projects(tmp_path):
    recent = tmp_path / "recent.json"
    p = create_project(tmp_path, "Hilang")
    add_recent(p, recent)
    (p.folder / "proyek.json").unlink()
    assert list_recent(recent) == []


def test_project_without_folder_does_not_save():
    p = Project("Tanpa folder")
    p.update_settings(tempo=100)
    assert p.tempo == 100
