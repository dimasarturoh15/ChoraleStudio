# HarmoniSATB Studio — Aturan Proyek

## Tentang proyek
Aplikasi desktop Windows untuk merekam paduan suara SATB (Sopran, Alto, Tenor, Bass) + piano secara overdub, lalu membuat master audio siap YouTube dengan satu klik. Spesifikasi lengkap: docs/PRD_v1.1.md. Mockup UI: design/.

## Bahasa
- Selalu jawab pengguna dalam Bahasa Indonesia, dengan bahasa sederhana (pengguna bukan engineer audio).
- Nama variabel/fungsi/kelas: bahasa Inggris. Komentar kode dan docstring: Bahasa Indonesia.
- Semua teks yang tampil di UI: Bahasa Indonesia, persis seperti di PRD dan mockup.

## Stack (jangan diganti tanpa izin)
- Python 3.12, virtual environment di .venv
- Audio I/O: sounddevice (PortAudio), soundfile, numpy
- DSP: pedalboard, scipy, pyloudnorm; DeepFilterNet opsional
- FFmpeg via paket imageio-ffmpeg (untuk MP3 dan verifikasi ebur128)
- UI: PySide6 (BUKAN PyQt6)
- Tes: pytest
- Paket: PyInstaller + Inno Setup

## Struktur folder
- src/chorale/audio/      → engine real-time (perangkat, rekam, putar, metronom, kalibrasi)
- src/chorale/project/    → model proyek, take, simpan/buka
- src/chorale/dsp/        → rantai pascaproduksi, mastering, pengukuran, ekspor
- src/chorale/ui/         → antarmuka PySide6
- tools/                  → skrip uji hardware & benchmark
- tests/                  → pytest
- docs/                   → PRD, PROGRESS.md, catatan teknis

## Aturan teknis wajib
- Sample rate dikunci 48000 Hz, rekaman 24-bit, pemrosesan internal float32.
- Callback audio TIDAK boleh: alokasi memori besar, I/O disk, logging, atau menyentuh objek Qt. Gunakan queue/ring buffer dan thread terpisah untuk tulis disk.
- Rekaman ditulis ke disk terus-menerus selama merekam (maksimal 1 detik hilang jika listrik padam).
- Prioritas driver: ASIO (jika ada) → WASAPI Exclusive → WASAPI Shared.
- Suara penyanyi sendiri TIDAK diputar ulang oleh software (monitoring vokal lewat tombol direct monitor sound card).
- Prioritas mastering: True Peak ≤ -1.0 dBTP (mutlak) > -14 LUFS ±1 > LRA (hanya dilaporkan).
- Engine DSP harus bisa dijalankan dari baris perintah tanpa UI.
- Tidak ada fitur di luar PRD (pitch correction, punch-in, VST, dll. dilarang).

## Windows & path
- Proyek berada di "D:\My Project\ChoraleStudio" (ada spasi). Selalu beri tanda kutip pada path di perintah terminal, dan utamakan path relatif.
- Gunakan pathlib di kode, jangan string path manual.

## Mockup UI
- Gambar di design/ adalah acuan tata letak, warna, urutan elemen, dan teks.
- Jangan meniru cacat mockup: teks terpotong ("Piano/O..."), teks turun baris, atau bagian kanan yang terpotong. Jendela utama 1440x900 dan semua teks harus tampil utuh.
- Bentuk gelombang di mockup hanya ilustrasi; di aplikasi digambar dari audio asli.

## Alur kerja setiap segmen
1. Baca CLAUDE.md, docs/PROGRESS.md, dan bagian PRD yang relevan.
2. Tulis rencana singkat (maks. 10 poin) sebelum mulai.
3. Kerjakan, lalu tulis/jalankan tes.
4. Perbarui docs/PROGRESS.md: apa yang selesai, hasil tes, masalah terbuka, keputusan teknis.
5. Commit dengan pesan Bahasa Indonesia yang jelas, lalu git push.
6. Laporkan ke pengguna: ringkasan, hasil tes, dan apa yang perlu ia lakukan/cek secara manual.

## Larangan
- Jangan commit file audio (.wav/.mp3), .venv, folder build/dist, atau model AI.
- Jangan menghapus file atau mengubah riwayat git (force push, reset --hard) tanpa izin pengguna.
- Jangan memasang paket di luar daftar stack tanpa menjelaskan alasannya dulu.
