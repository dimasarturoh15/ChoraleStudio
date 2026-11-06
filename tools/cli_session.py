"""CLI HarmoniSATB Studio (pengganti UI sementara): proyek, rekam, putar, take.

Contoh:
    python tools\\cli_session.py buat "Bapa Engkau Sungguh Baik" --tempo 72 --birama 4/4
    python tools\\cli_session.py info
    python tools\\cli_session.py rekam piano
    python tools\\cli_session.py rekam bass
    python tools\\cli_session.py putar
    python tools\\cli_session.py daftar-take bass
    python tools\\cli_session.py pilih-take bass 1
    python tools\\cli_session.py atur bass --volume -3 --solo tidak --mute tidak

Tanpa --proyek, perintah memakai proyek yang terakhir dibuka. Saat merekam
atau memutar, tekan Enter (atau Ctrl+C) untuk berhenti.
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools._common import ROOT, setup_console  # noqa: E402
from chorale.audio.calibration import load_calibrations  # noqa: E402
from chorale.audio.device import BLOCKSIZE_CHOICES, DEFAULT_BLOCKSIZE, AudioDeviceError, select_device  # noqa: E402
from chorale.audio.meter import meter_zone  # noqa: E402
from chorale.audio.metronome import DEFAULT_VOLUME_DB  # noqa: E402
from chorale.audio.session import AudioSession  # noqa: E402
from chorale.project import TRACK_IDS, TRACK_LABELS, add_recent, create_project, list_recent, open_project  # noqa: E402
from chorale.project.model import COUNT_IN_CHOICES, TIME_SIGNATURES  # noqa: E402

try:
    import msvcrt
except ImportError:  # bukan Windows: berhenti hanya lewat Ctrl+C
    msvcrt = None


def stop_key_pressed() -> bool:
    if msvcrt is None:
        return False
    while msvcrt.kbhit():
        if msvcrt.getwch() in ("\r", "\n", " ", "\x1b"):
            return True
    return False


def fmt_time(seconds: float) -> str:
    m, s = divmod(max(0.0, seconds), 60)
    return f"{int(m):02d}:{s:04.1f}"


def bar(db: float, width: int = 20) -> str:
    filled = int(max(0.0, min(1.0, (db + 60) / 60)) * width)
    return "#" * filled + "-" * (width - filled)


def load(args):
    if args.proyek:
        project = open_project(Path(args.proyek))
    else:
        recent = list_recent()
        if not recent:
            sys.exit("Belum ada proyek. Buat dulu: python tools\\cli_session.py buat \"Judul Lagu\"")
        project = open_project(Path(recent[0]["path"]))
    add_recent(project)
    return project


# ----- perintah -----

def cmd_buat(args) -> int:
    folder = Path(args.folder)
    folder.mkdir(parents=True, exist_ok=True)
    project = create_project(folder, args.judul, tempo=args.tempo, time_signature=args.birama,
                             count_in_bars=args.hitungan_awal,
                             metronome_after_count_in=not args.metronom_berhenti)
    add_recent(project)
    print(f"Proyek dibuat: {project.folder}")
    return cmd_info(args, project)


def cmd_info(args, project=None) -> int:
    project = project or load(args)
    print(f"\n  {project.title}")
    print(f"  Folder         : {project.folder}")
    print(f"  Tempo          : {project.tempo} BPM   Birama: {project.time_signature}")
    print(f"  Hitungan awal  : {project.count_in_bars} bar   Metronom setelah hitungan awal: "
          f"{'ya' if project.metronome_after_count_in else 'tidak'}")
    print(f"  Diubah         : {project.modified_at}\n")
    print(f"  {'Track':<12} {'Status':<10} {'Take aktif':<18} {'Jml':>3}  {'Volume':>7}  S M")
    for track in project.tracks.values():
        take = track.active_take
        status = "terekam" if take else "kosong"
        active = (take.label + ("" if take.complete else " (!)")) if take else "-"
        print(f"  {track.label:<12} {status:<10} {active:<18} {len(track.takes):>3}  "
              f"{track.volume_db:+6.1f} dB  {'S' if track.solo else '.'} {'M' if track.mute else '.'}")
    cals = load_calibrations()
    print(f"\n  Kalibrasi latensi tersimpan: {len(cals)}"
          + "".join(f"\n    - {c.hostapi} {'Exclusive' if c.exclusive else 'Shared'}, buffer {c.blocksize}: "
                    f"{c.latency_samples} sampel ({c.latency_ms:.2f} ms), {c.input_device}" for c in cals))
    print()
    return 0


def cmd_daftar_take(args) -> int:
    project = load(args)
    tracks = [args.track] if args.track else TRACK_IDS
    for tid in tracks:
        track = project.track(tid)
        print(f"\n  {track.label}:")
        if not track.takes:
            print("    (belum ada take)")
        for t in track.takes:
            mark = "*" if t.id == track.active_take_id else " "
            status = "lengkap" if t.complete else "TIDAK lengkap"
            print(f"   {mark} {t.label:<16} {t.duration:7.2f} s  {status:<14} {t.filename}")
    print("\n  * = take aktif")
    return 0


def cmd_pilih_take(args) -> int:
    project = load(args)
    try:
        project.set_active_take(args.track, args.nomor)
    except KeyError as exc:
        print(f"  {exc.args[0]}")
        return 1
    print(f"  Take aktif {TRACK_LABELS[args.track]} sekarang: Take {args.nomor}")
    return 0


def cmd_atur(args) -> int:
    project = load(args)
    try:
        if args.volume is not None:
            project.set_volume(args.track, args.volume)
        if args.solo is not None:
            project.set_solo(args.track, args.solo == "ya")
        if args.mute is not None:
            project.set_mute(args.track, args.mute == "ya")
    except ValueError as exc:
        print(f"  {exc}")
        return 1
    tr = project.track(args.track)
    print(f"  {tr.label}: volume {tr.volume_db:+.1f} dB, solo {'ya' if tr.solo else 'tidak'}, "
          f"mute {'ya' if tr.mute else 'tidak'}")
    return 0


def _select(args):
    try:
        return select_device(args.device)
    except AudioDeviceError as exc:
        print(f"  {exc}")
        return None


def _run_session(session: AudioSession, stop_at: float | None, show_inputs: list[int]) -> None:
    """Jalankan sesi sampai Enter/Ctrl+C/batas waktu, sambil menampilkan meter teks."""
    spb = session.metronome.samples_per_beat
    try:
        while True:
            time.sleep(0.1)
            st = session.status()
            if st.device_lost:
                print("\n  Sound card terputus!")
                break
            if st.in_count_in:
                beats_left = math.ceil(-st.song_seconds * 48000 / spb)
                line = f"  Hitungan awal ... {beats_left:>2}"
            else:
                meters = []
                for ch in show_inputs:
                    db = float(st.peaks_db[ch])
                    clip = " CLIP" if st.clip[ch] else ""
                    meters.append(f"in{ch + 1} [{bar(db)}] {db:6.1f} {meter_zone(db):<7}{clip}")
                label = "REKAM" if session.recorder else "PUTAR"
                line = f"  {label} {fmt_time(st.song_seconds)}  " + "  ".join(meters)
            print("\r" + line.ljust(110), end="", flush=True)
            if stop_key_pressed():
                break
            if stop_at is not None and st.song_seconds >= stop_at:
                break
    except KeyboardInterrupt:
        pass
    print()


def cmd_rekam(args) -> int:
    project = load(args)
    selection = _select(args)
    if selection is None:
        return 1
    first = args.input - 1
    channels = 1 if (args.track != "piano" or args.mono) else None
    try:
        session = AudioSession(
            project, selection, record_track=args.track, blocksize=args.buffer,
            input_first_channel=first, record_channels=channels,
            monitor_gain_db=args.volume_musik, metronome=False if args.tanpa_metronom else None,
            metronome_volume_db=args.volume_metronom,
        )
    except ValueError as exc:
        print(f"  {exc}")
        return 1

    rec_ch = session.recorder.channels
    print(f"\n  Rekam {TRACK_LABELS[args.track]} ({'stereo' if rec_ch == 2 else 'mono'}, "
          f"input {args.input}{'-' + str(args.input + 1) if rec_ch == 2 else ''})")
    print(f"  Sound card : {selection.mode_label}, buffer {args.buffer}")
    print(f"  Tempo {project.tempo} BPM, {project.time_signature}, hitungan awal {project.count_in_bars} bar")
    if args.track != "piano":
        print("  Suara Anda sendiri TIDAK diputar aplikasi; dengarkan lewat tombol direct monitor.")
    for w in session.warnings:
        print(f"  PERINGATAN: {w}")

    stop_at = args.detik
    if stop_at is None and args.track != "piano" and session.playback_length_seconds > 0:
        stop_at = session.playback_length_seconds + 1.0
        print(f"  Berhenti otomatis di {fmt_time(stop_at)} (akhir piano + 1 detik), atau tekan Enter.")
    else:
        print("  Tekan Enter untuk berhenti.")
    if not args.yes:
        input("  Tekan Enter untuk mulai... ")

    try:
        session.start()
    except AudioDeviceError as exc:
        print(f"  Gagal membuka sound card: {exc}")
        return 1
    _run_session(session, stop_at, list(range(first, first + rec_ch)))
    take = session.stop()

    if take is None:
        print("  Tidak ada audio yang terekam (berhenti saat hitungan awal?).")
        return 1
    print(f"  Tersimpan  : {take.label}, {take.duration:.2f} detik, "
          f"{'lengkap' if take.complete else 'TIDAK lengkap'} -> {take.filename}")
    print(f"  Latensi    : digeser {take.latency_compensation} sampel "
          f"({take.latency_compensation / 48:.2f} ms, dari {session.latency_source})")
    print(f"  Dropout    : {session.dropouts}")
    for w in session.warnings:
        print(f"  PERINGATAN: {w}")
    return 0


def cmd_putar(args) -> int:
    project = load(args)
    selection = _select(args)
    if selection is None:
        return 1
    session = AudioSession(project, selection, blocksize=args.buffer, start_seconds=args.dari,
                           monitor_gain_db=args.volume_musik, metronome=args.metronom,
                           metronome_volume_db=args.volume_metronom, count_in=False)
    if session.playback_length_seconds == 0:
        print("  Belum ada track terekam (atau semua di-mute).")
        return 1
    end = session.playback_length_seconds if args.detik is None else min(
        session.playback_length_seconds, args.dari + args.detik)
    print(f"  Putar {fmt_time(args.dari)} - {fmt_time(end)}. Tekan Enter untuk berhenti.")
    try:
        session.start()
    except AudioDeviceError as exc:
        print(f"  Gagal membuka sound card: {exc}")
        return 1
    _run_session(session, end, [])
    session.stop()
    return 0


def main() -> int:
    setup_console()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    parser.add_argument("--proyek", help="folder proyek (default: proyek terakhir)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("buat", help="buat proyek baru")
    p.add_argument("judul")
    p.add_argument("--tempo", type=int, default=72)
    p.add_argument("--birama", choices=TIME_SIGNATURES, default="4/4")
    p.add_argument("--hitungan-awal", type=int, choices=COUNT_IN_CHOICES, default=2)
    p.add_argument("--metronom-berhenti", action="store_true", help="metronom berhenti setelah hitungan awal")
    p.add_argument("--folder", default=str(ROOT / "projects"))
    p.set_defaults(func=cmd_buat)

    p = sub.add_parser("info", help="info proyek")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("daftar-take", help="daftar take")
    p.add_argument("track", nargs="?", choices=TRACK_IDS)
    p.set_defaults(func=cmd_daftar_take)

    p = sub.add_parser("pilih-take", help="pilih take aktif")
    p.add_argument("track", choices=TRACK_IDS)
    p.add_argument("nomor", type=int)
    p.set_defaults(func=cmd_pilih_take)

    p = sub.add_parser("atur", help="volume/solo/mute track")
    p.add_argument("track", choices=TRACK_IDS)
    p.add_argument("--volume", type=float, help="dB, -12 s.d. +6")
    p.add_argument("--solo", choices=("ya", "tidak"))
    p.add_argument("--mute", choices=("ya", "tidak"))
    p.set_defaults(func=cmd_atur)

    for name, func in (("rekam", cmd_rekam), ("putar", cmd_putar)):
        p = sub.add_parser(name, help=f"{name} lewat sound card")
        if name == "rekam":
            p.add_argument("track", choices=TRACK_IDS)
            p.add_argument("--mono", action="store_true", help="rekam piano mono (keyboard 1 output)")
            p.add_argument("--input", type=int, default=1, help="nomor input pertama (default 1)")
            p.add_argument("--tanpa-metronom", action="store_true", help="metronom mati setelah hitungan awal")
            p.add_argument("--yes", action="store_true", help="langsung mulai tanpa menunggu Enter")
            p.set_defaults(func=func)
        else:
            p.add_argument("--dari", type=float, default=0.0, help="mulai dari detik ke-")
            p.add_argument("--metronom", action="store_true", help="bunyikan metronom saat memutar")
            p.set_defaults(func=func)
        p.add_argument("--detik", type=float, help="berhenti otomatis setelah sekian detik lagu")
        p.add_argument("--volume-metronom", type=float, default=DEFAULT_VOLUME_DB)
        p.add_argument("--volume-musik", type=float, default=0.0)
        p.add_argument("--buffer", type=int, choices=BLOCKSIZE_CHOICES, default=DEFAULT_BLOCKSIZE)
        p.add_argument("--device", default="SC202", help="kata kunci nama sound card")

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
