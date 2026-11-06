# HarmoniSATB Studio (ChoraleStudio)

Aplikasi desktop Windows untuk merekam paduan suara 4 suara (Sopran, Alto, Tenor, Bass) bersama piano/orgen secara bergiliran (overdub), lalu menghasilkan master audio siap YouTube (WAV 24-bit/48 kHz dan MP3 320 kbps, sekitar −14 LUFS, puncak ≤ −1 dBTP) dengan satu klik.

- Spesifikasi: [docs/PRD_v1.1.md](docs/PRD_v1.1.md)
- Progres pengembangan: [docs/PROGRESS.md](docs/PROGRESS.md)
- Mockup UI: [design/](design/)

## Kebutuhan

- Windows 10/11 64-bit
- Python 3.12 (cek dengan `py -0`)

## Setup

Jalankan dari folder proyek (path mengandung spasi, jadi selalu pakai tanda kutip):

```powershell
cd "D:\My Project\ChoraleStudio"
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pip install -e .
```

## Menjalankan aplikasi

```powershell
.venv\Scripts\python -m chorale
```

## Menjalankan tes

```powershell
.venv\Scripts\python -m pytest
```

## Struktur folder

| Folder | Isi |
|---|---|
| `src/chorale/audio/` | Engine real-time: perangkat, rekam, putar, metronom, kalibrasi |
| `src/chorale/project/` | Model proyek, take, simpan/buka |
| `src/chorale/dsp/` | Rantai pascaproduksi, mastering, pengukuran, ekspor |
| `src/chorale/ui/` | Antarmuka PySide6 |
| `tools/` | Skrip uji hardware & benchmark |
| `tests/` | Tes pytest |
| `docs/` | PRD, progres, catatan teknis |

## Alat uji & CLI (sementara, sebelum UI)

```powershell
.venv\Scripts\python tools\list_devices.py          # perangkat & dukungan ASIO
.venv\Scripts\python tools\test_wasapi.py           # buka sound card di WASAPI Exclusive/Shared
.venv\Scripts\python tools\calibrate_latency.py     # ukur latensi (butuh kabel loopback)
.venv\Scripts\python tools\sync_test.py             # uji sinkron 5 track (butuh kabel loopback)
.venv\Scripts\python tools\stress_test.py --minutes 60
.venv\Scripts\python tools\cli_session.py --help    # buat proyek, rekam, putar, pilih take
.venv\Scripts\python tools\make_demo_project.py     # proyek contoh SATB sintetis
.venv\Scripts\python tools\process_project.py       # proses proyek -> master WAV + MP3 + laporan
.venv\Scripts\python tools\benchmark.py            # ukur waktu produce() untuk lagu 4 menit
.venv\Scripts\python tools\ui_screenshots.py         # screenshot tiap layar -> docs\screenshots
```

## Dokumen

- [Panduan pengguna](docs/PANDUAN_PENGGUNA.md): dari instalasi sampai ekspor, bergambar
- [Checklist uji lapangan](docs/UJI_LAPANGAN.md): uji bersama paduan suara (kriteria penerimaan PRD bagian 10)

## Membuat installer

Butuh **Inno Setup 6** (gratis): unduh dari https://jrsoftware.org/isdl.php, atau jalankan
`winget install --id JRSoftware.InnoSetup -e` di PowerShell.

```powershell
.venv\Scripts\python -m pip install -r requirements-build.txt
.venv\Scripts\python tools\build_installer.py
```

Hasil:
- `dist\HarmoniSATB Studio\`: aplikasi siap jalan (PyInstaller onedir) + folder `licenses\`
- `installer\Output\HarmoniSATB-Studio-<versi>-Setup.exe`: installer (shortcut Start Menu & Desktop; data di `%APPDATA%\HarmoniSATB` dan folder proyek tidak dihapus saat uninstall)

Skrip build otomatis menguji aplikasi hasil build tanpa Python di PATH, termasuk
`"HarmoniSATB Studio.exe" --uji-mandiri` (5 track sintetis → WAV + MP3 + laporan; kode keluar 0 = lulus).

## Log

Log aplikasi ada di `%APPDATA%\HarmoniSATB\logs\` (berotasi, 5 × 1 MB). Bisa juga dibuka lewat
Pengaturan → Tentang Aplikasi → Buka Folder Log.
