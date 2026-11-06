"""Benchmark produce(): proyek sintetis 5 track x 4 menit (gerbang Sprint 2: <= 60 detik).

Proyek dibuat di folder sementara dan dihapus di akhir (kecuali --simpan).

Cara pakai:
    .venv\\Scripts\\python tools\\benchmark.py [--menit 4] [--ulang 1] [--simpan]
"""

from __future__ import annotations

import argparse
import math
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools._common import heading, setup_console  # noqa: E402
from tools.make_demo_project import BAR, create_demo  # noqa: E402
from chorale.dsp.produce import STEP_LABELS, produce  # noqa: E402

LIMIT_S = 60.0


def main() -> int:
    setup_console()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--menit", type=float, default=4.0, help="panjang lagu uji (default 4)")
    parser.add_argument("--ulang", type=int, default=1, help="jumlah pengulangan")
    parser.add_argument("--simpan", action="store_true", help="jangan hapus proyek uji")
    args = parser.parse_args()

    workdir = Path(tempfile.mkdtemp(prefix="harmonisatb_bench_"))
    bars = math.ceil(args.menit * 60 / BAR)
    print(f"  Membuat proyek uji sintetis: 5 track, {bars} birama ({bars * BAR / 60:.2f} menit)...")
    project = create_demo(workdir, "Benchmark", bars=bars)

    heading("Benchmark produce()")
    print(f"  CPU: {os.cpu_count()} inti logis. Peredam derau: tidak terpasang (tahap 1 dilewati).")
    results = []
    try:
        for run in range(1, args.ulang + 1):
            marks: list[tuple[int, float]] = []
            start = time.perf_counter()

            def progress(step: int, pct: float) -> None:
                if not marks or marks[-1][0] != step:
                    marks.append((step, time.perf_counter() - start))

            r = produce(project, progress=progress)
            total = time.perf_counter() - start
            results.append(total)
            print(f"\n  Percobaan {run}: {total:.1f} detik  "
                  f"(master {r.mastered.integrated_lufs:.1f} LUFS, {r.mastered.true_peak_dbtp:.2f} dBTP)")
            ends = [t for _, t in marks[1:]] + [total]
            for (step, t0), t1 in zip(marks, ends):
                print(f"    {step}. {STEP_LABELS[step]:<36} {t1 - t0:5.1f} s")
    finally:
        if args.simpan:
            print(f"\n  Proyek uji disimpan di: {project.folder}")
        else:
            shutil.rmtree(workdir, ignore_errors=True)

    best = min(results)
    print()
    print(f"  Waktu terbaik: {best:.1f} detik (batas {LIMIT_S:.0f} detik untuk lagu 4 menit)")
    print("  -> LULUS" if best <= LIMIT_S else "  -> TIDAK LULUS")
    print()
    return 0 if best <= LIMIT_S else 1


if __name__ == "__main__":
    sys.exit(main())
