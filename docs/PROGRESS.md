# Progres HarmoniSATB Studio

Rujukan: [PRD_v1.1.md](PRD_v1.1.md). Daftar segmen di bawah adalah rancangan awal yang dipetakan dari Rencana Pengembangan PRD (Bagian 8) dan bisa disesuaikan.

| Segmen | Cakupan | Sprint PRD | Status |
|---|---|---|---|
| 0 | Fondasi proyek: CLAUDE.md, struktur folder, .venv, requirements, README | — | ✅ Selesai |
| 1 | Cek SC202HD & driver, uji rekam-putar 48 kHz via sounddevice (tools/) | 0 | Belum |
| 2 | Engine audio CLI: rekam ke disk terus-menerus, playback cue, metronom & count-in | 1 | Belum |
| 3 | Kalibrasi latensi, kompensasi sinkron ≤ 1 ms, model proyek & take (FR-9) | 0–1 | Belum |
| 4 | Pascaproduksi FR-5 & FR-6: HPF, EQ, kompresor, penyeimbang, panning, reverb | 2 | Belum |
| 5 | Mastering FR-7, pengukuran (LUFS/TP/LRA), ekspor & laporan FR-8, verifikasi ebur128 | 2 | Belum |
| 6 | UI PySide6: jendela utama 5 bilah track, VU meter, transport | 3 | Belum |
| 7 | UI: daftar proyek, proyek baru, pengaturan perangkat, panduan rekam, proses & hasil/A-B | 3 | Belum |
| 8 | Uji lapangan dengan paduan suara, perbaikan bug, uji penerimaan (Bagian 10) | 4 | Belum |
| 9 | Paket PyInstaller + installer Inno Setup | 4 | Belum |

---

## Segmen 0 — Fondasi proyek (selesai, 2026-11-06)

**Yang dikerjakan**
- CLAUDE.md (aturan proyek), README.md, pyproject.toml (konfigurasi pytest), requirements.txt dengan versi dikunci.
- Paket `src/chorale/{audio,project,dsp,ui}` dan folder `tools/`, `tests/`, masing-masing dengan `__init__.py`.
- `.venv` dengan Python 3.12.1.
- PRD disalin dari PDF ke `docs/PRD_v1.1.md` agar mudah dibaca dan dirujuk (PDF asli tetap ada).
- `.gitignore` dilengkapi.

**Versi terpasang**

| Paket | Versi |
|---|---|
| Python | 3.12.1 |
| sounddevice | 0.5.6 (PortAudio V19.7.0) |
| soundfile | 0.14.0 (libsndfile 1.2.2) |
| numpy | 2.5.4 |
| scipy | 1.18.1 |
| pedalboard | 0.9.26 |
| pyloudnorm | 0.2.0 |
| imageio-ffmpeg | 0.8.1 (FFmpeg 9.0.2) |
| PySide6 | 6.12.0 |
| pytest | 9.2.0 |

**Hasil tes**: `tests/test_imports.py` — semua modul ter-import, biner FFmpeg tersedia.

**Masalah terbuka / catatan untuk segmen berikutnya**
- PortAudio bawaan wheel sounddevice di Windows hanya menyediakan host API MME, DirectSound, WASAPI, dan WDM-KS — **tanpa ASIO**. Jika ASIO resmi SC202HD ternyata tersedia, perlu DLL PortAudio yang dikompilasi dengan ASIO (dibahas di Segmen 1). Tanpa itu, WASAPI Exclusive menjadi jalur utama, sesuai cadangan di PRD.
- DeepFilterNet belum dipasang; akan dievaluasi di Segmen 4 (perhatikan ukuran installer ≤ 1,5 GB).

**Keputusan teknis**
- Versi paket dikunci (`==`) agar build bisa diulang.
- pytest memakai `pythonpath = ["src", "."]` di pyproject.toml, jadi tidak perlu `pip install -e .`.
