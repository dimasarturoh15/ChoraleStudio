# Arsitektur HarmoniSATB Studio

Dokumen ini menjelaskan cara kerja aplikasi di balik layar, untuk pengembang yang ingin membaca, menguji, atau mengubah kodenya. Kebutuhan produk ada di [PRD_v1.1.md](PRD_v1.1.md); dokumen ini menjelaskan bagaimana kebutuhan itu diwujudkan.

## Daftar isi

- [Gambaran umum](#gambaran-umum)
- [Peta modul](#peta-modul)
- [Model thread](#model-thread)
- [Engine audio real-time](#engine-audio-real-time)
- [Rantai pascaproduksi](#rantai-pascaproduksi)
- [Mastering](#mastering)
- [Pengukuran](#pengukuran)
- [Ekspor](#ekspor)
- [Format proyek](#format-proyek)
- [Data aplikasi](#data-aplikasi)
- [Penanganan error dan log](#penanganan-error-dan-log)
- [Antarmuka](#antarmuka)
- [Pemaketan](#pemaketan)
- [Pengujian](#pengujian)
- [Keputusan desain](#keputusan-desain)

## Gambaran umum

Aplikasi terdiri atas tiga lapisan yang tidak saling bergantung ke atas:

```text
┌──────────────────────────────── chorale.ui (PySide6) ────────────────────────────────┐
│ daftar proyek · proyek baru · layar rekam · persiapan vokal · proses · hasil · pengaturan │
└───────────┬───────────────────────────────────────────────────────┬──────────────────┘
            │ QTimer 30 fps: membaca keadaan engine                 │ QThread: produce()
            ▼                                                       ▼
┌──── chorale.audio (real-time) ────┐                 ┌──── chorale.dsp (offline) ────┐
│ device   pemilihan driver & stream │                 │ chain    tahap 1-6 per track   │
│ session  rekam + putar + metronom  │                 │ master   kompresor bus+limiter │
│ recorder ring buffer → WAV         │                 │ measure  LUFS · TP · LRA       │
│ player   campuran monitoring       │                 │ export   WAV · MP3 · FFmpeg    │
│ meter    puncak & lampu clip       │                 │ produce  orkestrasi + laporan  │
│ calibration  latensi loopback      │                 └───────────────┬───────────────┘
└─────────────────┬─────────────────┘                                 │
                  ▼                                                   ▼
         ┌────────────── chorale.project ──────────────┐
         │ proyek.json · takes/ · master/ · recent.json │
         └──────────────────────────────────────────────┘
```

- `chorale.audio` dan `chorale.dsp` tidak meng-import Qt sama sekali, sehingga mesin rekam dan mesin pengolah bisa dipakai dari baris perintah (`tools/cli_session.py`, `tools/process_project.py`) dan diuji tanpa antarmuka.
- `chorale.ui` hanya memanggil API publik kedua lapisan itu.

## Peta modul

| Modul | Tanggung jawab |
|---|---|
| `audio/device.py` | Mengaktifkan PortAudio ber-ASIO (`SD_ENABLE_ASIO=1` sebelum `sounddevice` di-import), mencari sound card, memilih host API sesuai prioritas, membuka stream duplex, menerjemahkan error PortAudio menjadi pesan Indonesia |
| `audio/session.py` | Satu sesi rekam atau putar: garis waktu lagu, hitungan awal, kompensasi latensi, callback |
| `audio/recorder.py` | `RingBuffer` satu penulis satu pembaca, thread penulis WAV 24-bit, cek ruang disk |
| `audio/player.py` | Memuat take aktif dan membuat campuran monitoring sebelum stream dimulai |
| `audio/metronome.py` | Klik metronom yang dicampur ke output saja |
| `audio/meter.py` | Puncak per kanal dan lampu clip yang bertahan |
| `audio/calibration.py` | Sweep, estimasi jeda dengan korelasi silang, penyimpanan per perangkat |
| `audio/ab_player.py` | Pemutar Mentah vs Master dengan kelantangan disamakan |
| `project/model.py` | `Project`, `Track`, `Take`; simpan otomatis setiap perubahan |
| `project/store.py` | Membuat dan membuka proyek, memulihkan take yatim, daftar proyek terakhir |
| `dsp/chain.py` | Tahap 1 sampai 6 per track dan `process_project()` |
| `dsp/balance.py`, `dsp/stereo.py`, `dsp/reverb.py`, `dsp/denoise.py` | Penyeimbang LUFS, pan, reverb konvolusi, peredam derau opsional |
| `dsp/master.py` | Kompresor bus, pencarian gain, limiter True Peak, gain A/B |
| `dsp/measure.py` | LUFS terintegrasi (BS.1770-4), True Peak teroversampling, LRA |
| `dsp/export.py` | Tulis WAV dengan dither, encode MP3, decode, verifikasi FFmpeg `ebur128` |
| `dsp/produce.py` | Orkestrasi pascaproduksi, mastering, ekspor, dan laporan |
| `dsp/presets.py` | Konstanta ringan (preset ruang, target, label langkah) yang aman di-import antarmuka |
| `ui/*` | Layar, overlay modal, tema, font, ikon, bentuk gelombang |
| `logging_setup.py` | Log berotasi, `faulthandler`, hook error |
| `selftest.py` | Uji mandiri `--uji-mandiri` |
| `licenses.py` | Data komponen pihak ketiga untuk halaman Tentang |

## Model thread

| Thread | Pemilik | Boleh melakukan |
|---|---|---|
| Callback PortAudio | `audio/session.py` | Menyalin buffer putar ke output, menambah klik metronom, menghitung puncak, menyalin input ke ring buffer. **Tidak** boleh alokasi besar, akses disk, logging, atau menyentuh Qt |
| Penulis WAV | `audio/recorder.py` | Membaca ring buffer, menulis ke `soundfile`, memperbarui header setiap ≤ 1 detik |
| UI (utama) | Qt | Membaca keadaan engine lewat `QTimer` 30 fps (posisi, level, status), menggambar |
| `ProduceWorker` (`QThread`) | `ui/processing.py` | Menjalankan `produce()`; melapor kemajuan lewat sinyal Qt; bisa dibatalkan |
| `CalibrationWorker` (`QThread`) | `ui/settings_screen.py` | Menjalankan kalibrasi latensi |
| `QThreadPool` | `ui/waveform.py` | Menghitung puncak bentuk gelombang, dengan cache per berkas |
| `MuatDSP` (daemon) | `ui/app.py` | Meng-import modul DSP 3 detik setelah jendela tampil |

Engine tidak pernah memancarkan sinyal Qt dari callback. Antarmuka selalu menarik (polling) keadaan, sehingga callback tetap bebas dari Qt.

## Engine audio real-time

### Pemilihan perangkat dan driver

1. Sound card dicari dengan kata kunci (`SC202`, `SPL`) atau nama yang disimpan di pengaturan.
2. Host API dicoba berurutan: **ASIO** → **WASAPI Exclusive** → **WASAPI Shared**, kecuali pengguna memilih mode tertentu.
3. Stream dibuka sebagai duplex 48 000 Hz float32 dengan buffer 128, 256 (default), 512, atau 1024 sampel.
4. Error PortAudio umum (sample rate tidak didukung, perangkat sibuk, format ditolak) diterjemahkan menjadi pesan dengan langkah perbaikan.

### Garis waktu sesi

Frame 0 adalah awal birama pertama setelah hitungan awal. Stream dimulai `count_in_frames` sebelum frame 0, jadi selama hitungan awal posisi lagu negatif. Semua persiapan berat (memuat take aktif, mencampur track monitoring, membuat berkas take) dilakukan sebelum stream dimulai; callback hanya menyalin dari buffer yang sudah jadi.

### Kompensasi latensi

Sinyal yang dikirim ke output pada frame lagu *p* baru terekam di input pada frame *p + L*, dengan *L* adalah latensi round-trip hasil kalibrasi. Perekam karena itu mulai menyimpan input pada frame lagu *L*, sehingga sampel pertama berkas take sejajar dengan frame 0 track lain.

Pergeseran dilakukan **saat merekam**, bukan sesudahnya, agar berkas di disk selalu sudah sejajar, termasuk bila listrik padam di tengah rekaman. Jumlah sampel yang dibuang dicatat di `latency_compensation` pada take.

### Jalur rekaman dan keamanan data

```text
callback ──copy──► RingBuffer (4 detik) ──► thread penulis ──► soundfile (WAV PCM_24)
                                                   └─ setiap ≤ 1 s: SFC_UPDATE_HEADER_NOW + flush
```

- Bila ring buffer penuh karena disk tertinggal, sampel yang hilang dihitung dan dilaporkan; stress test memeriksa angka ini selalu nol.
- Bila sound card tercabut, sesi berhenti, perekam menulis sisa buffer, lalu durasi take diambil dari berkas yang benar-benar tertulis.
- Take yang terhenti tidak normal ditandai `complete: false`. Berkas take tanpa entri di `proyek.json` (take yatim, misalnya karena aplikasi mati) dipulihkan saat proyek dibuka.
- Sebelum merekam, ruang disk dicek; kurang dari 2 GB memunculkan peringatan.

### Monitoring

Saat merekam, output berisi campuran track lain yang tidak di-mute ditambah klik metronom. Suara penyanyi sendiri **tidak** diputar ulang; penyanyi mendengarnya lewat tombol direct monitor di sound card, sehingga latensi software tidak terasa saat bernyanyi.

### Kalibrasi latensi

Dengan kabel dari output ke input, aplikasi memutar sweep, merekamnya, dan mencari jeda dengan korelasi silang. Percobaan diulang beberapa kali dan hasilnya disimpan per kombinasi perangkat, host API, mode exclusive, dan ukuran buffer di `calibration.json`.

### Kanal acuan dan pemanasan (temuan uji SC202HD)

Driver USB generik pada SC202HD (chip Realtek, tanpa ASIO) memulai setiap stream dengan latensi berbeda (selisih 1 sampai sekitar 6 ms) dan kadang menggesernya di tengah stream tanpa laporan error. Kalibrasi sekali pakai tidak bisa menangkapnya. Dua pengaman:

- **Pemanasan** (`AudioSession(warmup_seconds=5)`): saat merekam, stream dimulai 5 detik sebelum hitungan awal; output hening dan tidak ada yang direkam. Ini menyerap pergeseran di detik-detik pertama stream.
- **Kanal acuan** (`AudioSession(reference_channel=...)`, `chorale/audio/alignment.py`, opsi "Kanal acuan sinkronisasi" di Pengaturan): saat merekam vokal, kabel Output → input yang tidak dipakai mikrofon direkam ke berkas pendamping `<take>_acuan.wav` lewat ring buffer kedua (callback hanya menyalin). Saat Stop:

```text
acuan[i]  ~= diputar[i - e]          e = latensi sebenarnya - latensi kalibrasi
take[i]   berisi frame musik i - e    (penyanyi mengikuti playback yang sama)
take'[q]  = take[q + e(q)]           e diukur per jendela 1 s tiap 0,5 s (korelasi ternormalisasi, +-100 ms)
```

Jendela yang acuannya pelan atau tidak jelas dilewati; lonjakan tunggal dibuang dengan median 3 titik; perubahan e lebih dari 8 sampel menjadi segmen baru, dan sambungan antar-segmen diberi fade 1 ms. Take ditulis ulang secara atomik (berkas sementara lalu `os.replace`), berkas acuan dihapus, dan `Take.alignment` bernilai `"acuan"`. Jika acuan tidak terdeteksi, take hasil kalibrasi dipertahankan dan pengguna mendapat peringatan. Track piano tidak memakai kanal acuan karena kedua input dipakai piano stereo; piano menjadi patokan bagi track vokal.

`tools/stress_test.py --loopback` mendeteksi lompatan latensi diam-diam selama uji panjang; `tools/sync_test.py --acuan` menguji kanal acuan dengan dua kabel loopback.

## Rantai pascaproduksi

`process_project()` memuat take aktif setiap track, menjalankan tahap berikut, lalu menjumlahkan semuanya menjadi campuran stereo. Track tanpa take dilewati.

| Tahap | Proses | Parameter | Track |
|---|---|---|---|
| 1 | Peredam derau (DeepFilterNet) | Opsional, dilewati bila paket tidak terpasang | Vokal |
| 2 | High-pass Butterworth orde 2 | Piano 35 Hz, Bass/Tenor 75 Hz, Alto/Sopran 90 Hz | Semua |
| 3 | EQ anti-boxiness | Peak -2 dB, 400 Hz, Q 1,0 | Vokal |
| 3 | Kompresor | 2,5:1, attack 25 ms, release 140 ms, reduksi maks 4 dB | Vokal |
| 4 | Penyeimbang | Vokal ke -23 LUFS, piano ke -25 LUFS, lalu offset slider -12 sampai +6 dB | Semua |
| 5 | Pan constant-power | Tenor -0,25, Sopran -0,12, Bass +0,12, Alto +0,25; piano tengah dengan lebar 0,65 | Semua |
| 6 | Reverb konvolusi | IR sintetis, pre-delay 32 ms, redaman 5 kHz; wet 12/20/30% | Bus |

Preset ruang menentukan waktu peluruhan (RT60) respons impuls: Gereja Kecil 1,6 s, Aula 2,0 s, Katedral 2,4 s. Respons impuls dibuat oleh kode dari derau dengan seed tetap, sehingga selalu sama untuk preset yang sama dan bebas masalah lisensi rekaman IR.

## Mastering

`master()` di `dsp/master.py` bekerja dengan prioritas yang tidak boleh dibalik:

1. **True Peak ≤ -1,0 dBTP (mutlak).**
2. **-14 LUFS ±1 (diusahakan).**
3. **LRA (hanya dilaporkan).**

Langkahnya:

1. Kompresor bus 1,5:1, attack 30 ms, release 250 ms, reduksi maks 2 dB.
2. Puncak teroversampling 4 kali dihitung **sekali** dan dipakai ulang untuk setiap gain yang dicoba.
3. Pencarian gain (maks 6 iterasi): gain awal = -14 LUFS dikurangi kelantangan saat ini. Untuk setiap gain, kurva limiter dihitung dengan target -1,15 dBTP (batas -1,0 dikurangi margin 0,15 dB agar pengukur lain juga membaca di bawah -1,0).
   - Bila limiter harus menekan lebih dari **6 dB**, gain diturunkan dan target LUFS dilepas. Laporan menjelaskan bahwa materinya terlalu dinamis.
   - Bila tidak, gain dikoreksi sampai kelantangan setelah limiter berada dalam ±0,1 LU dari -14.
4. Limiter lookahead 5 ms, release 100 ms, dengan gain dihitung per blok 1 ms.
5. Kelantangan, True Peak, dan LRA hasil akhir diukur ulang dengan pengukur penuh.

## Pengukuran

| Ukuran | Implementasi |
|---|---|
| LUFS terintegrasi | Filter K-weighting BS.1770-4 untuk 48 kHz, gating absolut -70 LUFS dan relatif -10 LU; `pyloudnorm` sebagai acuan di tes |
| True Peak | Oversampling 4 kali dengan filter polyphase |
| LRA | EBU Tech 3342 (blok 3 detik, persentil 10 dan 95) |
| Verifikasi | FFmpeg `ebur128=peak=true` pada WAV hasil ekspor; dinyatakan cocok bila selisih ≤ 0,2 |

## Ekspor

- **Nama berkas**: `<judul aman>_<YYYYMMDD-HHMM>_Master.wav`, `..._Master.mp3`, `..._Laporan.txt`. Bila nama sudah dipakai, ditambah akhiran `-2`, `-3`, dan seterusnya. Berkas lama tidak pernah ditimpa.
- **Ekor**: campuran diperpanjang sampai ekor reverb turun di bawah -60 dB, lalu ditambah 1 detik hening.
- **WAV**: PCM 24-bit, 48 kHz, stereo, dengan dither TPDF.
- **MP3**: FFmpeg + LAME 320 kbps CBR dengan tag judul. MP3 hasil encoding didekode dan diukur ulang; bila puncaknya melewati -1,0 dBTP, MP3 dibuat ulang sedikit lebih pelan (maks 4 percobaan) dan hal itu dicatat sebagai peringatan.
- **Atomik**: bila proses dibatalkan atau gagal, ketiga berkas yang sedang dibuat dihapus.
- **Paralel**: encoding MP3 dan verifikasi FFmpeg berjalan bersamaan di dua thread.

## Format proyek

Satu proyek = satu lagu = satu folder:

```text
Bapa Engkau Sungguh Baik/
├── proyek.json
├── takes/
│   ├── piano_take1_20261106-215310.wav
│   ├── bass_take1_20261106-220102.wav
│   └── bass_take2_20261106-220544.wav
└── master/
    ├── Bapa_Engkau_Sungguh_Baik_20261106-2230_Master.wav
    ├── Bapa_Engkau_Sungguh_Baik_20261106-2230_Master.mp3
    └── Bapa_Engkau_Sungguh_Baik_20261106-2230_Laporan.txt
```

`proyek.json` (skema versi 1) ditulis secara atomik setiap kali ada perubahan:

```json
{
  "version": 1,
  "title": "Bapa Engkau Sungguh Baik",
  "tempo": 72,
  "time_signature": "4/4",
  "count_in_bars": 2,
  "metronome_after_count_in": true,
  "room_preset": "katedral",
  "reverb_amount": "normal",
  "vocal_guide_done": false,
  "created_at": "2026-11-06T21:50:02",
  "modified_at": "2026-11-06T21:53:10",
  "tracks": [
    {
      "id": "piano",
      "active_take_id": 1,
      "volume_db": 0.0,
      "solo": false,
      "mute": false,
      "denoise": true,
      "takes": [
        {
          "id": 1,
          "filename": "piano_take1_20261106-215310.wav",
          "recorded_at": "2026-11-06T21:53:10",
          "duration": 183.4,
          "complete": true,
          "latency_compensation": 0
        }
      ]
    }
  ]
}
```

| Kolom | Nilai |
|---|---|
| `tracks[].id` | `piano` (2 kanal), `bass`, `tenor`, `alto`, `sopran` (1 kanal); selalu kelimanya |
| `tempo` | 40 sampai 240 |
| `time_signature` | `2/4`, `3/4`, `4/4`, `6/8` |
| `count_in_bars` | 0, 1, 2 |
| `room_preset` | `gereja_kecil`, `aula`, `katedral` |
| `reverb_amount` | `sedikit`, `normal`, `banyak` |
| `volume_db` | -12,0 sampai +6,0 |
| `takes[].filename` | `<track>_take<n>_<YYYYMMDD-HHMMSS>.wav`, WAV 24-bit 48 kHz |

## Data aplikasi

Semua berada di `%APPDATA%\HarmoniSATB\` dan tidak dihapus saat uninstall.

| Berkas | Isi |
|---|---|
| `settings.json` | Sound card, mode driver, ukuran buffer, pemetaan input instrumen dan vokal, folder proyek, volume metronom |
| `calibration.json` | Hasil kalibrasi latensi per perangkat, host API, mode, dan buffer |
| `recent.json` | Hingga 10 proyek terakhir |
| `logs\harmonisatb.log` | Log berotasi 5 × 1 MB |
| `logs\crash.log` | Keluaran `faulthandler` bila proses crash di tingkat native |
| `ui-cache\` | Ikon SVG yang dibuat untuk stylesheet Qt |

Folder proyek bawaan: `Documents\HarmoniSATB\`.

## Penanganan error dan log

- `setup_logging()` dipanggil paling awal di `main()`.
- `sys.excepthook` dan `threading.excepthook` mencatat traceback lengkap ke log, lalu menampilkan dialog "Terjadi kesalahan" dengan tombol **Buka Folder Log**. Pengguna tidak pernah melihat traceback.
- Pesan dari thread non-UI diteruskan ke thread UI lewat sinyal `ErrorReporter`.
- Pesan Qt diteruskan ke log lewat `qInstallMessageHandler`.
- Pada aplikasi tanpa konsol, `stdout` dan `stderr` dialihkan ke log.

## Antarmuka

- Jendela utama 1440 × 900 (minimal 1280 × 800) dengan `QStackedWidget` untuk layar Daftar Proyek, Rekam, Hasil, dan Pengaturan.
- Dialog (Proyek Baru, Persiapan Rekam Vokal, Memproses Produksi, Sound card terputus) adalah overlay modal di dalam jendela, bukan jendela terpisah.
- Tema gelap dari `ui/style.qss` dengan token warna; font Inter dan JetBrains Mono disertakan; teks minimal 13 px; tombol rekam 72 px.
- Bentuk gelombang digambar dari audio asli dan dihitung di `QThreadPool` dengan cache per berkas.
- Saat ditutup, jendela dihapus eksplisit dengan `shiboken6.delete` selagi `QApplication` masih hidup, untuk mencegah crash urutan penghapusan saat interpreter keluar.

## Pemaketan

| Langkah | Alat | Hasil |
|---|---|---|
| Aplikasi | PyInstaller onedir, tanpa konsol (`installer/harmonisatb.spec`) | `dist\HarmoniSATB Studio\` (328 MB) |
| Lisensi | `tools/build_installer.py` | `licenses\` berisi teks lisensi setiap komponen dan `THIRD_PARTY_NOTICES.txt` |
| Uji asap | `tools/build_installer.py` | Buka-tutup jendela dan `--uji-mandiri` dengan PATH tanpa Python |
| Installer | Inno Setup 6 (`installer/HarmoniSATB.iss`) | `HarmoniSATB-Studio-<versi>-Setup.exe` (87 MB) |

Installer memakai `PrivilegesRequired=lowest` (per pengguna, tanpa admin, dengan pilihan untuk semua pengguna), memasang shortcut Start Menu dan Desktop, dan tidak memiliki bagian `[UninstallDelete]` agar data pengguna tidak terhapus.

Agar aplikasi cepat terbuka, antarmuka tidak meng-import SciPy atau pedalboard saat start (import `scipy.signal` memakan sekitar 11 detik di laptop uji). Konstanta yang dibutuhkan antarmuka ada di `dsp/presets.py`, dan modul DSP dimuat di thread latar setelah jendela tampil.

## Pengujian

| Lapisan | Tes | Cara |
|---|---|---|
| DSP dan mastering | `test_dsp.py`, `test_master.py` | Sinyal sintetis dengan nilai yang diketahui; dibandingkan dengan `pyloudnorm` dan FFmpeg |
| Engine audio | `test_recorder.py`, `test_session.py`, `test_player.py`, `test_metronome.py`, `test_sync.py`, `test_calibration.py`, `test_device.py` | Komponen diberi data sintetis secara langsung; tes sesi memakai stream palsu yang memanggil callback secara deterministik, tanpa sound card |
| Proyek | `test_project.py` | Folder sementara; termasuk pemulihan take yatim |
| Antarmuka | `test_ui.py`, `test_recording_ui.py`, `test_result_ui.py`, `test_flow.py` | Qt `offscreen`; alur penuh dari proyek baru sampai ekspor |
| Rilis | `test_release.py` | Versi, log, hook error, uji mandiri, halaman Tentang, skrip installer |

Uji yang membutuhkan perangkat nyata (`calibrate_latency.py`, `sync_test.py`, `stress_test.py`) dan uji bersama pengguna ([UJI_LAPANGAN.md](UJI_LAPANGAN.md)) dijalankan terpisah.

## Keputusan desain

| Keputusan | Alasan |
|---|---|
| Monitoring vokal lewat direct monitor perangkat keras | Latensi software 10 sampai 20 ms di WASAPI mengganggu penyanyi; perangkat keras tanpa latensi |
| WASAPI Exclusive sebagai cadangan utama, bukan ASIO4ALL | ASIO4ALL sering bentrok dengan aplikasi lain |
| True Peak di atas LUFS | Puncak di atas -1 dBTP bisa terdistorsi setelah encoding YouTube; kelantangan yang sedikit kurang hanya terdengar sedikit lebih pelan |
| Batas reduksi limiter 6 dB | Lebih dari itu merusak dinamika paduan suara |
| Tanpa gate atau ekspander | Memotong bagian lembut dan ekor reverb |
| Respons impuls sintetis | Bebas masalah lisensi dan deterministik |
| PySide6, bukan PyQt6 | LGPL lebih longgar untuk distribusi |
| Pergeseran latensi saat merekam | Berkas di disk selalu sejajar, termasuk bila listrik padam |
| DeepFilterNet ditunda | Dirancang untuk suara bicara; berisiko artefak pada nada panjang dan menambah ukuran installer |
