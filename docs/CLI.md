# Referensi alat baris perintah

Semua alat ada di folder `tools/` dan dijalankan dari akar repositori dengan Python virtual environment proyek:

```powershell
.venv\Scripts\python tools\<nama>.py [opsi]
```

Setiap alat menerima `--help`. Alat yang memakai sound card mencari SPL Audio SC202HD secara otomatis; gunakan `--device` dengan sebagian nama perangkat untuk memilih yang lain (misalnya `--device Realtek`).

## Daftar isi

- [Perangkat dan driver](#perangkat-dan-driver): `list_devices`, `test_wasapi`
- [Kalibrasi dan sinkronisasi](#kalibrasi-dan-sinkronisasi): `calibrate_latency`, `sync_test`
- [Stabilitas](#stabilitas): `stress_test`
- [Sesi rekam tanpa antarmuka](#sesi-rekam-tanpa-antarmuka): `cli_session`, `demo_record`
- [Data uji](#data-uji): `import_takes`, `make_demo_project`
- [Pascaproduksi](#pascaproduksi): `process_project`, `benchmark`
- [Rilis dan dokumentasi](#rilis-dan-dokumentasi): `build_installer`, `ui_screenshots`, `make_icon`
- [Aplikasi](#aplikasi): `HarmoniSATB Studio.exe --uji-mandiri`

## Perangkat dan driver

### `list_devices.py`

Menampilkan semua host API dan perangkat audio, menandai SC202HD, dan memeriksa apakah ASIO tersedia.

| Opsi | Keterangan |
|---|---|
| `--device TEKS` | Kata kunci nama perangkat yang ditandai |

### `test_wasapi.py`

Mencoba membuka sound card di WASAPI Exclusive, lalu Shared bila gagal, pada 48 kHz.

| Opsi | Keterangan |
|---|---|
| `--device TEKS` | Kata kunci nama perangkat |
| `--blocksize {128,256,512,1024}` | Ukuran buffer (default 256) |

## Kalibrasi dan sinkronisasi

Keduanya membutuhkan **kabel loopback** dari Output sound card ke Input 1. Matikan phantom +48V dan tombol direct monitor sebelum mulai, agar tidak terjadi dengung.

### `calibrate_latency.py`

Mengukur latensi round-trip (putar ke rekam) dan menyimpannya ke `%APPDATA%\HarmoniSATB\calibration.json`.

| Opsi | Keterangan |
|---|---|
| `--device TEKS` | Kata kunci nama perangkat |
| `--hostapi {wasapi,asio}` | Host API yang diuji |
| `--shared` | Pakai WASAPI Shared |
| `--blocksize {128,256,512,1024}` | Ukuran buffer |
| `--runs N` | Jumlah percobaan (default 5) |
| `--yes` | Lewati konfirmasi Enter |
| `--no-save` | Jangan simpan hasil |

### `sync_test.py`

Merekam klik metronom lewat loopback ke lima track lalu mengukur selisih antar-track. Lulus bila selisih ≤ 3 ms (PRD v1.1 rev. 1). Setiap track diawali pemanasan 5 detik seperti di aplikasi.

| Opsi | Keterangan |
|---|---|
| `--device TEKS` | Kata kunci nama perangkat |
| `--buffer {128,256,512,1024}` | Ukuran buffer |
| `--detik N` | Durasi setiap track |
| `--yes` | Lewati konfirmasi Enter |
| `--simpan` | Simpan proyek uji (default dihapus) |
| `--acuan` | Uji kanal acuan: kabel kedua Output R → Input 2; track vokal disejajarkan dengan kanal acuan seperti di aplikasi |

## Stabilitas

### `stress_test.py`

Merekam dan memutar bersamaan selama N menit, lalu menghitung dropout, sampel yang hilang di ring buffer, dan beban callback. Keluar dengan kode `0` bila tidak ada dropout.

| Opsi | Keterangan |
|---|---|
| `--device TEKS` | Kata kunci nama perangkat |
| `--blocksize {128,256,512,1024}` | Ukuran buffer |
| `--minutes N` | Durasi uji (default 10; kriteria PRD 60) |
| `--interval DETIK` | Jeda laporan kemajuan |
| `--simpan` | Jangan hapus proyek uji di akhir |
| `--loopback` | Dengan kabel loopback: metronom 60 BPM berbunyi sepanjang uji, lalu rekaman dianalisis tiap 10 detik untuk menemukan **lompatan latensi** yang tidak dilaporkan sebagai dropout (ditemukan pada SC202HD). Gagal bila ada lompatan lebih dari 0,5 ms |

```powershell
.venv\Scripts\python tools\stress_test.py --minutes 60 --blocksize 256
.venv\Scripts\python tools\stress_test.py --minutes 60 --loopback
```

## Sesi rekam tanpa antarmuka

### `cli_session.py`

Pengganti antarmuka untuk membuat proyek, merekam, memutar, dan memilih take. Opsi global `--proyek FOLDER` memilih proyek (default: proyek terakhir).

| Perintah | Kegunaan | Opsi |
|---|---|---|
| `buat JUDUL` | Membuat proyek baru | `--tempo`, `--birama {2/4,3/4,4/4,6/8}`, `--hitungan-awal {0,1,2}`, `--metronom-berhenti`, `--folder` |
| `info` | Menampilkan isi proyek | |
| `daftar-take` | Menampilkan semua take | |
| `pilih-take TRACK NOMOR` | Memilih take aktif | |
| `atur TRACK` | Mengatur volume, solo, mute | `--volume dB` (-12 sampai +6), `--solo {ya,tidak}`, `--mute {ya,tidak}` |
| `rekam TRACK` | Merekam satu track | `--mono`, `--input N`, `--tanpa-metronom`, `--detik N`, `--volume-metronom`, `--volume-musik`, `--buffer`, `--device`, `--yes` |
| `putar` | Memutar campuran | `--dari DETIK`, `--metronom`, `--detik N`, `--volume-metronom`, `--volume-musik`, `--buffer`, `--device` |

`TRACK` adalah salah satu dari `piano`, `bass`, `tenor`, `alto`, `sopran`.

```powershell
.venv\Scripts\python tools\cli_session.py buat "Bapa Engkau Sungguh Baik" --tempo 72 --birama 4/4
.venv\Scripts\python tools\cli_session.py rekam piano
.venv\Scripts\python tools\cli_session.py rekam bass
.venv\Scripts\python tools\cli_session.py pilih-take bass 2
.venv\Scripts\python tools\cli_session.py putar
```

### `demo_record.py`

Merekam beberapa detik dari mikrofon sambil memutar musik panduan, lalu menyimpannya ke proyek contoh. Berguna untuk mencoba alur rekam pertama kali.

| Opsi | Keterangan |
|---|---|
| `--seconds N` | Durasi rekam (default 10) |
| `--track {bass,tenor,alto,sopran}` | Track tujuan |
| `--device TEKS` | Kata kunci nama perangkat |
| `--input N` | Nomor input mikrofon (1 atau 2) |
| `--folder FOLDER` | Folder proyek contoh |
| `--monitor-gain-db dB` | Volume musik panduan di headphone |
| `--blocksize {128,256,512,1024}` | Ukuran buffer |
| `--yes` | Lewati konfirmasi Enter |

## Data uji

### `import_takes.py`

Mengimpor berkas WAV atau FLAC sebagai take, untuk mengisi lima track tanpa merekam.

| Opsi | Keterangan |
|---|---|
| `--proyek FOLDER` | Folder proyek (wajib) |
| `--piano`, `--bass`, `--tenor`, `--alto`, `--sopran` BERKAS | Berkas audio untuk setiap track |
| `--contoh` | Isi kelima track dengan suara sintetis |
| `--birama N` | Panjang contoh sintetis |

### `make_demo_project.py`

Membuat proyek "Contoh SATB" berisi lima track **sintetis** (bukan rekaman suara asli).

| Opsi | Keterangan |
|---|---|
| `--folder FOLDER` | Lokasi proyek |
| `--birama N` | Jumlah birama (72 = 4 menit) |

## Pascaproduksi

### `process_project.py`

Menjalankan rantai pascaproduksi, mastering, dan ekspor tanpa antarmuka, lalu mencetak hasil pengukuran.

| Opsi | Keterangan |
|---|---|
| `--proyek FOLDER` | Folder proyek (default: proyek terakhir) |
| `--ruang {gereja_kecil,aula,katedral}` | Preset ruang (default: dari proyek) |
| `--reverb {sedikit,normal,banyak}` | Jumlah reverb (default: dari proyek) |
| `--tanpa-denoise` | Matikan peredam derau semua track |
| `--tanpa-verifikasi` | Lewati pengukuran ulang dengan FFmpeg |

Kode keluar: `0` siap YouTube, `1` gagal, `2` berhasil tetapi target belum tercapai (lihat peringatan di laporan).

### `benchmark.py`

Mengukur waktu `produce()` untuk proyek sintetis lima track. Kriteria PRD: lagu 4 menit ≤ 60 detik.

| Opsi | Keterangan |
|---|---|
| `--menit N` | Panjang lagu uji (default 4) |
| `--ulang N` | Jumlah pengulangan |
| `--simpan` | Jangan hapus proyek uji |

## Rilis dan dokumentasi

### `build_installer.py`

Membuat aplikasi dengan PyInstaller, mengumpulkan teks lisensi pihak ketiga, menguji aplikasi hasil build dengan PATH tanpa Python, lalu membuat Setup.exe dengan Inno Setup 6.

| Opsi | Keterangan |
|---|---|
| `--lewati-installer` | Berhenti setelah PyInstaller dan uji asap |

Kode keluar: `0` berhasil, `1` uji asap gagal, `2` Inno Setup tidak ditemukan.

### `ui_screenshots.py`

Membuka setiap layar dalam mode tanpa tampilan dan menyimpan tangkapan layar untuk dibandingkan dengan mockup di `design/`.

| Opsi | Keterangan |
|---|---|
| `--out FOLDER` | Folder tujuan (default `docs\screenshots`) |

### `make_icon.py`

Membuat ikon aplikasi `src/chorale/ui/assets/harmonisatb.ico` (7 ukuran) dan `harmonisatb.png`.

## Aplikasi

| Perintah | Kegunaan |
|---|---|
| `"HarmoniSATB Studio.exe"` | Membuka aplikasi |
| `"HarmoniSATB Studio.exe" --uji-mandiri` | Memproses lima track sintetis sampai WAV, MP3, dan laporan tanpa sound card; kode keluar `0` bila lulus. Hasilnya ditulis ke `%APPDATA%\HarmoniSATB\logs\harmonisatb.log` |
| `.venv\Scripts\python -m chorale` | Membuka aplikasi dari kode sumber |
