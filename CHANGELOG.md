# Riwayat perubahan

Semua perubahan penting pada HarmoniSATB Studio dicatat di berkas ini. Formatnya mengikuti [Keep a Changelog](https://keepachangelog.com/id-ID/1.1.0/), dan nomor versi mengikuti [Semantic Versioning](https://semver.org/lang/id/).

## [Belum dirilis]

## [1.3.0] - 2026-11-08

### Ditambahkan

- Cek gain untuk setiap kelompok suara: saat pertama kali merekam suara vokal berikutnya, Persiapan Rekam Vokal terbuka langsung di langkah "Atur Gain Mic". Rekam ulang suara yang sama tidak ditanya lagi.

### Diperbaiki

- `tools/ui_screenshots.py` memperhitungkan pemanasan sound card dan cek gain; screenshot "Sound card terputus" kembali menampilkan detik rekaman yang benar (sebelumnya 00:00).

## [1.2.0] - 2026-11-07

Penyesuaian setelah uji dengan SPL Audio SC202HD.

### Ditambahkan

- **Kanal acuan sinkronisasi** (Pengaturan > Pemetaan Input): saat merekam vokal, kabel dari Output ke input yang tidak dipakai mikrofon dipakai untuk mengukur latensi sebenarnya setiap take, lalu take disejajarkan dengan piano, termasuk lompatan latensi di tengah lagu. Ditambah pengingat di Persiapan Rekam Vokal.
- Pemanasan sound card 5 detik sebelum hitungan awal saat merekam ("Menyiapkan sound card …").
- `tools/stress_test.py --loopback` (deteksi lompatan latensi diam-diam) dan `tools/sync_test.py --acuan`.

### Diubah

- Target sinkronisasi PRD menjadi ≤ 3 ms (PRD v1.1 rev. 1) setelah uji SPL Audio SC202HD.
- Panduan pengguna: persiapan laptop sebelum merekam (charger, aplikasi pengolah suara dimatikan, USB selective suspend dimatikan).
- Kalibrasi yang hasilnya berubah-ubah tidak lagi ditampilkan sebagai error merah: "Berubah-ubah" dengan penjelasan bila kanal acuan aktif, atau "Tidak konsisten" (kuning) dengan saran mengaktifkan kanal acuan.

### Diperbaiki

- Teks "Latensi terukur" menempel pada angka latensi saat kolom Pengaturan sempit.
- Ambang lompatan penyejajaran 8 → 24 sampel agar klik bernada berbeda tidak dibaca sebagai lompatan latensi.
- `installer/harmonisatb.spec` kini ikut di repositori. Sebelumnya terabaikan oleh aturan `*.spec` di `.gitignore`, sehingga installer tidak bisa dibuat dari hasil clone.

### Dokumentasi

- README ditulis ulang: fitur, tangkapan layar, kebutuhan sistem, instalasi, status kriteria penerimaan.
- Dokumen baru: [ARCHITECTURE.md](docs/ARCHITECTURE.md), [CLI.md](docs/CLI.md), [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), templat Issue dan pull request.

## [1.1.0] - 2026-11-06

Rilis pertama yang lengkap secara fitur sesuai [PRD v1.1](docs/PRD_v1.1.md), siap untuk uji lapangan.

### Ditambahkan

**Engine audio**
- Pemilihan driver otomatis ASIO → WASAPI Exclusive → WASAPI Shared, dengan PortAudio ber-ASIO.
- Sesi rekam dan putar dengan hitungan awal, metronom yang tidak ikut terekam, dan campuran monitoring yang disiapkan sebelum stream dimulai.
- Perekam dengan ring buffer dan thread penulis WAV 24-bit; header diperbarui setiap detik.
- Kalibrasi latensi lewat loopback dan kompensasi latensi saat merekam.
- Meter level dengan lampu clip yang bertahan; cek ruang disk sebelum merekam.
- Penanganan sound card tercabut saat merekam tanpa kehilangan audio yang sudah masuk.

**Proyek**
- Satu proyek per lagu (`proyek.json`, `takes/`, `master/`) dengan simpan otomatis, daftar take, take aktif, dan pemulihan take yatim.
- Daftar proyek terakhir.

**Pascaproduksi dan mastering**
- Rantai tujuh tahap: peredam derau opsional, high-pass, EQ anti-boxiness, kompresor, penyeimbang LUFS, pan constant-power, reverb konvolusi dengan respons impuls sintetis.
- Preset ruang Gereja Kecil, Aula, Katedral dan jumlah reverb Sedikit, Normal, Banyak.
- Mastering dengan kompresor bus dan limiter True Peak oversampling 4 kali; prioritas True Peak > LUFS > LRA; batas reduksi limiter 6 dB.
- Pengukuran BS.1770-4 / EBU R128 dan verifikasi independen dengan FFmpeg `ebur128`.
- Ekspor WAV 24-bit dengan dither TPDF, MP3 320 kbps yang diukur ulang, dan laporan berbahasa Indonesia; ekor reverb utuh; tidak pernah menimpa.

**Antarmuka**
- Layar Daftar Proyek, Proyek Baru, Pengaturan (Perangkat Audio, Tentang Aplikasi), Layar Rekam lima track, Persiapan Rekam Vokal, Memproses Produksi, dan Hasil Produksi dengan pemutar Mentah vs Master.
- Tema gelap sesuai mockup, font Inter dan JetBrains Mono, bentuk gelombang dari audio asli.

**Rilis**
- Installer Inno Setup per pengguna tanpa hak admin; data pengguna tidak dihapus saat uninstall.
- Log berotasi, dialog error ramah, dan `--uji-mandiri`.
- Halaman Tentang dengan daftar lisensi pihak ketiga.
- [Panduan pengguna](docs/PANDUAN_PENGGUNA.md) dan [checklist uji lapangan](docs/UJI_LAPANGAN.md).
- Alat baris perintah untuk uji perangkat keras, stress test, benchmark, sesi tanpa antarmuka, dan build.

### Diubah

- Waktu buka aplikasi dipercepat dari sekitar 26 menjadi sekitar 10 detik dengan memuat modul DSP di latar.
- Teks petunjuk monitoring disesuaikan dengan SC202HD yang memakai tombol direct monitor ON/OFF, bukan kenop.

### Diperbaiki

- Track yang sedang direkam tidak dibersihkan bila Stop ditekan saat sesi masih disiapkan.
- Durasi tersimpan saat sound card tercabut diukur sebelum penulis disk selesai.
- Crash saat keluar setelah membuka popup di layar Pengaturan.

### Diketahui

- Uji dengan SPL Audio SC202HD (kalibrasi, sinkronisasi, stress test, rekaman nyanyian) belum dilakukan.
- DeepFilterNet belum dipakai.

[Belum dirilis]: https://github.com/dimasarturoh15/ChoraleStudio/compare/v1.3.0...HEAD
[1.3.0]: https://github.com/dimasarturoh15/ChoraleStudio/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/dimasarturoh15/ChoraleStudio/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/dimasarturoh15/ChoraleStudio/releases/tag/v1.1.0
