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
