# Berkontribusi ke HarmoniSATB Studio

Terima kasih sudah tertarik membantu. Dokumen ini menjelaskan cara melaporkan masalah, menyiapkan lingkungan pengembangan, dan mengirim perubahan.

Repositori ini belum memiliki lisensi open-source (lihat [README](README.md#hak-cipta-dan-komponen-pihak-ketiga)). Dengan mengirim pull request, Anda setuju perubahan tersebut boleh dipakai dan didistribusikan oleh pemilik proyek sebagai bagian dari HarmoniSATB Studio.

## Daftar isi

- [Melaporkan bug](#melaporkan-bug)
- [Mengusulkan perubahan](#mengusulkan-perubahan)
- [Lingkungan pengembangan](#lingkungan-pengembangan)
- [Aturan teknis wajib](#aturan-teknis-wajib)
- [Gaya kode](#gaya-kode)
- [Tes](#tes)
- [Antarmuka](#antarmuka)
- [Commit dan pull request](#commit-dan-pull-request)
- [Yang tidak boleh di-commit](#yang-tidak-boleh-di-commit)

## Melaporkan bug

Buka [Issue baru](https://github.com/dimasarturoh15/ChoraleStudio/issues/new/choose) dengan templat **Laporan bug** dan sertakan:

- Versi aplikasi (Pengaturan > Tentang Aplikasi) dan versi Windows.
- Sound card dan mode driver yang tampil di bagian atas layar rekam (misalnya `WASAPI Exclusive · 48 kHz · 24-bit · 12 ms`).
- Langkah untuk memunculkan masalah, hasil yang diharapkan, dan yang terjadi.
- Berkas `%APPDATA%\HarmoniSATB\logs\harmonisatb.log` (tombol **Buka Folder Log** ada di halaman Tentang dan di dialog error).

Jangan lampirkan rekaman suara orang lain tanpa izin mereka.

## Mengusulkan perubahan

Cakupan versi 1.1 ditetapkan oleh [PRD](docs/PRD_v1.1.md). Fitur di luar PRD, misalnya koreksi nada, punch-in, plug-in VST, atau efek tambahan, **tidak** diterima. Bila Anda punya ide fitur, buka Issue dengan templat **Usulan** terlebih dulu untuk didiskusikan sebagai bahan PRD versi berikutnya.

Perbaikan bug, peningkatan keandalan, performa, aksesibilitas, tes, dan dokumentasi selalu diterima.

## Lingkungan pengembangan

Kebutuhan: Windows 10/11 64-bit, Python 3.12, Git. Sound card hanya dibutuhkan untuk uji perangkat keras.

```powershell
git clone https://github.com/dimasarturoh15/ChoraleStudio.git
cd ChoraleStudio
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pip install -e .
```

Menjalankan aplikasi: `.venv\Scripts\python -m chorale`.

Untuk membuat installer, pasang juga `requirements-build.txt` dan [Inno Setup 6](https://jrsoftware.org/isdl.php). Paket di luar stack (lihat [CLAUDE.md](CLAUDE.md#stack-jangan-diganti-tanpa-izin)) tidak ditambahkan tanpa diskusi lebih dulu.

## Aturan teknis wajib

Aturan ini dijaga oleh tes dan tinjauan; perubahan yang melanggarnya tidak digabungkan.

1. **Format audio dikunci**: 48 000 Hz, rekaman 24-bit, pemrosesan internal float32.
2. **Callback audio bersih**: tanpa alokasi memori besar, tanpa I/O disk, tanpa logging, tanpa menyentuh objek Qt. Gunakan ring buffer dan thread terpisah.
3. **Rekaman ditulis terus-menerus**: paling banyak 1 detik hilang bila listrik padam.
4. **Prioritas driver**: ASIO → WASAPI Exclusive → WASAPI Shared.
5. **Suara penyanyi tidak diputar ulang oleh software.** Monitoring vokal lewat tombol direct monitor sound card.
6. **Prioritas mastering**: True Peak ≤ -1,0 dBTP (mutlak) > -14 LUFS ±1 > LRA (hanya dilaporkan).
7. **Mesin DSP bisa dijalankan tanpa antarmuka**: `chorale.audio` dan `chorale.dsp` tidak boleh meng-import Qt.
8. **Path dengan pathlib**, bukan string; repositori dan folder proyek boleh mengandung spasi.

Penjelasan alasan di balik aturan ini ada di [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#keputusan-desain).

## Gaya kode

- Nama variabel, fungsi, dan kelas dalam **bahasa Inggris**.
- Komentar dan docstring dalam **Bahasa Indonesia**. Tulis komentar hanya untuk menjelaskan batasan yang tidak terlihat dari kode, bukan untuk mengulang apa yang dilakukan baris berikutnya.
- Python 3.12 dengan anotasi tipe.
- Panjang baris dianjurkan tidak lebih dari 120 karakter.
- Konstanta audio (frekuensi, rasio, target) ditaruh sebagai konstanta bernama di awal modul, dengan satuan di nama atau komentar (`HPF_CUTOFF_HZ`, `RELEASE_S`).
- Modul yang di-import antarmuka saat start tidak boleh meng-import SciPy atau pedalboard di tingkat modul (memperlambat pembukaan aplikasi). Gunakan `dsp/presets.py` atau import di dalam fungsi.

## Tes

```powershell
.venv\Scripts\python -m pytest -q
```

- Semua tes harus lulus tanpa sound card. Antarmuka diuji dengan `QT_QPA_PLATFORM=offscreen`.
- Setiap perbaikan bug disertai tes regresi.
- Perubahan DSP disertai tes dengan sinyal sintetis yang hasilnya diketahui. Perubahan mastering wajib menjaga True Peak ≤ -1,0 dBTP pada semua sinyal uji di `tests/test_master.py`.
- Perubahan pada engine real-time diuji juga dengan `tools/stress_test.py --minutes 10` (atau 60 untuk rilis) pada perangkat nyata, dan hasilnya ditulis di deskripsi pull request.
- Perubahan yang memengaruhi kecepatan proses dijalankan dengan `tools/benchmark.py` (batas 60 detik untuk lagu 4 menit).

## Antarmuka

- Teks antarmuka dalam Bahasa Indonesia, sesuai PRD dan mockup di `design/`.
- Jendela utama 1440 × 900 (minimal 1280 × 800); semua teks harus tampil utuh, tanpa terpotong atau turun baris.
- Ukuran teks minimal 13 px; tombol rekam minimal 64 × 64 px.
- Setelah mengubah tampilan, jalankan `tools/ui_screenshots.py` dan sertakan tangkapan layar sebelum dan sesudah di pull request.
- Pesan error untuk pengguna ditulis dengan bahasa sederhana beserta langkah perbaikannya. Detail teknis hanya ke log.

## Commit dan pull request

- Buat branch dari `main`, misalnya `perbaikan/meter-clip` atau `dokumen/arsitektur`.
- Pesan commit dalam **Bahasa Indonesia**, kalimat pertama ringkas (maksimal sekitar 70 karakter), lalu baris kosong dan penjelasan bila perlu.
- Satu pull request untuk satu perubahan yang utuh. Isi templat pull request, termasuk hasil tes.
- Perbarui [docs/PROGRESS.md](docs/PROGRESS.md) bila perubahan menyentuh kriteria penerimaan, dan [CHANGELOG.md](CHANGELOG.md) di bagian *Belum dirilis*.
- Jangan mengubah riwayat branch `main` (force push, rebase yang sudah dipublikasikan).

## Yang tidak boleh di-commit

- Berkas audio (`.wav`, `.mp3`, `.flac`, dan sejenisnya) dan folder proyek rekaman.
- `.venv/`, `build/`, `dist/`, `installer/Output/`.
- Model AI (`.pt`, `.onnx`, dan sejenisnya).
- Data pribadi, rekaman orang lain, atau kredensial.

Aturan ini sudah dijaga oleh `.gitignore`; periksa `git status` sebelum commit.
