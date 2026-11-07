# PRD HarmoniSATB Studio v1.1

Nov 6, 2026 · Dimas Arturoh

> Salinan Markdown dari `docs/PRD HarmoniSATB Studio v1.1.pdf`. Jika ada perbedaan, PDF adalah acuan asli,
> kecuali perubahan yang tercatat di tabel riwayat versi di akhir dokumen (keputusan setelah PDF dibuat).

## Perubahan dari v1.0

Versi 1.1 menyesuaikan PRD dengan hardware yang benar-benar dimiliki (SPL Audio SC202HD) dan membuang fitur yang tidak realistis, sehingga dokumen ini siap dipakai untuk mulai membangun aplikasi.

| Area | v1.0 | v1.1 |
|---|---|---|
| Sound card | SPL Crimson/Creon (ASIO wajib) | SPL Audio SC202HD; ASIO jika tersedia, WASAPI Exclusive sebagai cadangan |
| Pitch correction | Wajib (polifonik ±15 cents) | Dihapus dari v1.1; nada meleset diatasi dengan re-take |
| Monitoring vokal | Software "zero-latency" + tombol virtual | Tombol direct monitor fisik di sound card |
| Balance antar-track | Tidak ditentukan | Auto-balance + slider volume per track |
| Target mastering | LUFS, TP, LRA setara (bertabrakan) | Prioritas: TP > LUFS > LRA (LRA hanya dilaporkan) |
| Reverb | Tanpa rasio wet/dry | Wet/dry ditetapkan + 3 preset ruang |
| Ekspander/gate | Memotong sinyal di bawah vokal | Dihapus (merusak bagian lembut & ekor reverb) |
| Manajemen proyek | Tidak ada | Proyek per lagu, pemilihan take, nama file unik |
| Jadwal | 7 minggu | 10 minggu |

## 1. Ringkasan Eksekutif

HarmoniSATB Studio adalah aplikasi desktop Windows untuk merekam paduan suara 4 suara (Sopran, Alto, Tenor, Bass) bersama piano/orgen secara bergiliran (overdubbing), lalu menghasilkan master audio siap YouTube dengan satu klik.

Aplikasi menyederhanakan studio rekaman menjadi 5 tombol rekam (Piano, Bass, Tenor, Alto, Sopran) dan 1 tombol produksi. Targetnya adalah paduan suara gereja, komunitas vokal, dan sekolah yang tidak punya studio maupun teknisi audio.

Hasil akhir: file WAV 24-bit/48 kHz dan MP3 320 kbps dengan kelantangan sekitar −14 LUFS dan puncak tidak melebihi −1 dBTP.

## 2. Lingkungan Perangkat Keras

Aplikasi dirancang untuk SPL Audio SC202HD, tetapi tidak bergantung pada merek: sound card USB apa pun yang dikenali Windows tetap bisa dipakai.

| Perangkat | Spesifikasi | Peran |
|---|---|---|
| Sound card | SPL Audio SC202HD (USB), 44,1–192 kHz, gain mic 56 dB, EIN −128 dB | Konversi audio 24-bit/48 kHz, phantom +48V, monitoring headphone |
| Mikrofon | Condenser large-diaphragm, phantom +48V | Merekam 2–4 penyanyi per suara |
| Headphone | Closed-back, 1 unit per penyanyi aktif (via headphone splitter/amp) | Mendengar musik panduan tanpa bocor ke mic |
| Instrumen | Digital piano/keyboard via kabel line/instrumen | Track panduan harmoni dan tempo |
| PC/Laptop | Windows 10/11 64-bit, CPU quad-core ≥2,5 GHz, RAM ≥8 GB, SSD disarankan | Menjalankan aplikasi dan proses DSP |

### Strategi driver

Aplikasi mendeteksi driver secara otomatis dengan urutan prioritas berikut:

1. ASIO resmi SC202HD, jika tersedia dari produsen/penjual.
2. WASAPI Exclusive (bawaan Windows): pilihan default jika ASIO resmi tidak ada. Tidak perlu instal apa pun.
3. WASAPI Shared: cadangan terakhir, hanya untuk uji coba.

ASIO4ALL tidak direkomendasikan karena sering bentrok dengan aplikasi lain. Karena penyanyi mendengar suaranya sendiri lewat tombol direct monitor fisik, latensi software sekitar 10–20 ms pada WASAPI tidak mengganggu perekaman.

### Hal yang harus dicek pada unit SC202HD

- Jumlah input yang bisa direkam terpisah di Windows (diasumsikan 2 kanal).
- Ada tombol direct monitor atau mix monitor fisik di panel depan.
- Driver ASIO resmi tersedia atau tidak.
- Dapat dikunci di 48 kHz / 24-bit dari pengaturan Windows.

## 3. Alur Kerja Pengguna

Pengguna membuat satu proyek per lagu, merekam 5 track secara berurutan, lalu menekan satu tombol untuk menghasilkan master.

1. **Buat/buka proyek**: isi judul lagu, tempo, dan birama. Aplikasi memeriksa sound card, driver, dan sample rate 48 kHz.
2. **Kalibrasi latensi** (sekali per perangkat): kabel output dihubungkan ke input, aplikasi mengukur jeda rekam-putar otomatis. Hasilnya disimpan untuk semua proyek.
3. **Rekam Piano/Orgen**: metronom count-in 1–2 bar, lalu piano direkam stereo sebagai track panduan. Metronom boleh dimatikan untuk lagu bertempo bebas.
4. **Rekam vokal berurutan** (Bass → Tenor → Alto → Sopran): tiap kelompok mendengar piano + suara yang sudah direkam di headphone, dan suaranya sendiri lewat tombol direct monitor sound card.
5. **Pilih take terbaik**: tiap track bisa direkam ulang berkali-kali; pengguna memilih take aktif dari daftar.
6. **Proses Produksi & Master**: satu klik menjalankan pembersihan, penyeimbangan, panning, reverb, dan mastering.
7. **Dengarkan & sesuaikan**: bandingkan Mentah vs Master (volume disamakan). Jika perlu, geser slider volume track atau ganti preset ruang, lalu proses ulang.
8. **Ekspor**: WAV, MP3, dan laporan tersimpan di folder proyek.

## 4. Kebutuhan Fungsional

Sembilan kelompok fitur berikut adalah cakupan penuh v1.1; fitur di luar daftar ini tidak dikerjakan.

### FR-1: Audio I/O & Driver

- Deteksi otomatis driver dengan urutan ASIO → WASAPI Exclusive → WASAPI Shared; pengguna bisa mengganti manual di menu Pengaturan.
- Sample rate dikunci 48.000 Hz, perekaman 24-bit, pemrosesan internal float 32-bit.
- Pemetaan input bisa dipilih: Instrumen = 2 kanal stereo (atau 1 kanal mono jika keyboard hanya 1 output), Vokal = 1 kanal mono dari input mikrofon.
- Buffer default 256 sampel; pilihan 128 / 256 / 512 / 1024.
- VU meter real-time per input: hijau −42 s.d. −12 dBFS, kuning −12 s.d. −3 dBFS, merah di atas −3 dBFS, dengan lampu clip yang tetap menyala sampai diklik.
- Penanganan error: perangkat dicabut saat merekam (rekaman yang sudah masuk tetap tersimpan), sample rate perangkat bukan 48 kHz (tampilkan cara memperbaiki), disk tersisa < 2 GB (peringatan sebelum rekam).

### FR-2: Antarmuka 5 Track

- 5 bilah: Piano/Orgen, Bass, Tenor, Alto, Sopran.
- Tiap bilah: tombol Rekam (abu-abu = kosong, merah berkedip = merekam, hijau = terekam), Solo, Mute, slider volume (−12 s.d. +6 dB), dan daftar take.
- Re-take tidak menghapus take lama; semua take disimpan dengan stempel waktu dan pengguna memilih take aktif.
- Track vokal tidak bisa direkam sebelum track Piano ada (piano = panduan wajib).
- Urutan vokal disarankan Bass → Sopran, tetapi tidak dikunci.
- Tombol Stop, Putar, dan kembali ke awal; tampilan waveform sederhana per track.

### FR-3: Monitoring Headphone

- Saat merekam, aplikasi memutar campuran track lain yang tidak di-mute ke output headphone sound card.
- Suara penyanyi sendiri tidak diputar ulang oleh aplikasi; penyanyi mendengarnya lewat tombol direct monitor fisik sound card.
- Layar menampilkan petunjuk singkat cara menyalakan tombol monitor sebelum merekam vokal.
- Rekaman baru otomatis digeser sesuai hasil kalibrasi latensi agar sejajar sampel-per-sampel dengan track sebelumnya.

### FR-4: Metronom & Count-In

- Tempo 40–240 BPM, birama 2/4, 3/4, 4/4, 6/8.
- Count-in 0, 1, atau 2 bar; metronom bisa dimatikan setelah count-in (untuk lagu rubato).
- Bunyi metronom hanya ke headphone dan tidak ikut terekam ke file.
- Volume metronom terpisah dari volume musik.

### FR-5: Rantai Pascaproduksi Otomatis

Urutan pemrosesan per track vokal (piano hanya melewati tahap 2, 6, dan 7):

| Tahap | Proses | Parameter default |
|---|---|---|
| 1 | Peredam derau (DeepFilterNet) | Reduksi maksimal 12 dB; bisa dimatikan per track |
| 2 | High-pass filter | Piano 35 Hz, Bass 75 Hz, Tenor 75 Hz, Alto 90 Hz, Sopran 90 Hz (12 dB/okt) |
| 3 | EQ anti-boxiness | −2 dB di 400 Hz, Q 1,0 |
| 4 | Kompresor | Rasio 2,5:1, attack 25 ms, release 140 ms, reduksi maks ±4 dB |
| 5 | Penyeimbang level (FR-6) | Tiap stem disamakan kelantangannya, lalu ditambah offset slider |
| 6 | Panning | Tenor 25% L, Sopran 12% L, Bass 12% R, Alto 25% R, Piano tengah dengan lebar stereo 65%; pan law constant-power −3 dB |
| 7 | Reverb konvolusi (bus kirim) | Preset Katedral: decay 2,4 s, pre-delay 32 ms, redaman tinggi 5 kHz, wet 20% |

Preset ruang yang tersedia: Gereja Kecil (decay 1,6 s), Aula (2,0 s), Katedral (2,4 s, default). Pengguna bisa memilih preset dan mengatur jumlah reverb (Sedikit / Normal / Banyak).

File impulse response harus berlisensi bebas royalti atau dibuat sendiri (sintetis); sumber dan lisensinya dicatat di folder aplikasi.

### FR-6: Penyeimbangan Antar-Track

- Tiap stem vokal diukur kelantangannya (LUFS terintegrasi) dan disamakan ke −23 LUFS.
- Piano disetel 2 LU di bawah stem vokal (−25 LUFS), agar vokal tetap di depan.
- Offset dari slider volume track (FR-2) diterapkan setelah penyamaan otomatis.
- Pengguna bisa memproses ulang tanpa merekam ulang; waktu proses ulang mengikuti target FR-5.

### FR-7: Mastering YouTube

Prioritas target, dari yang paling wajib:

1. **True Peak ≤ −1,0 dBTP (mutlak)**: limiter dengan oversampling 4×.
2. **Kelantangan −14 LUFS ±1 (diusahakan)**: dinaikkan dengan limiter. Jika untuk mencapainya limiter harus menekan lebih dari 6 dB, aplikasi berhenti di level yang lebih pelan dan mencatatnya di laporan.
3. **LRA** (hanya diukur dan dilaporkan, tidak dipaksa).

Sebelum limiter ada kompresor bus ringan (rasio 1,5:1, reduksi maks 2 dB). Pengukuran mengikuti ITU-R BS.1770-4 / EBU R128.

### FR-8: Ekspor

- `<Judul>_<YYYYMMDD-HHMM>_Master.wav`: PCM 24-bit, 48 kHz, stereo, dengan dither TPDF.
- `<Judul>_<YYYYMMDD-HHMM>_Master.mp3`: 320 kbps CBR, dengan tag judul.
- `<Judul>_<YYYYMMDD-HHMM>_Laporan.txt`: LUFS terintegrasi, True Peak, LRA, durasi, reduksi limiter maksimum, preset ruang, dan peringatan jika target LUFS tidak tercapai.
- Render diperpanjang sampai ekor reverb turun di bawah −60 dB, ditambah 1 detik hening; tidak ada pemotongan ekor.
- Ekspor tidak pernah menimpa file lama.

### FR-9: Manajemen Proyek

- Satu proyek = satu lagu = satu folder: `proyek.json`, `takes/`, `master/`.
- Buat, buka, simpan otomatis, dan daftar proyek terakhir.
- Pemutar A/B Mentah vs Master dengan volume disamakan (loudness-matched) agar perbandingan adil.

## 5. Kebutuhan Non-Fungsional

Semua target di bawah ini terukur dan diuji pada perangkat kelas Intel Core i5 dengan SC202HD. Target waktu proses dinaikkan dari 35 ke 60 detik karena DeepFilterNet berjalan di CPU untuk 4 track vokal.

| Parameter | Target | Cara uji |
|---|---|---|
| Waktu proses | ≤ 60 detik untuk lagu 4 menit (5 track) | Benchmark otomatis dengan file uji standar |
| Stabilitas audio | 0 dropout selama 60 menit pada buffer 256 sampel | Stress test rekam + putar |
| Keamanan rekaman | Data ditulis ke disk terus-menerus selama merekam; maksimal 1 detik hilang jika listrik padam | Uji cabut daya/USB saat merekam |
| Sinkronisasi | Selisih antar-track ≤ 3 ms setelah kalibrasi | Rekam klik loopback, ukur selisih |
| Kemudahan pakai | Tombol rekam ≥ 64×64 px, tema gelap kontras tinggi, terbaca dari jarak 1,5 m | Uji pengguna dengan anggota paduan suara |
| Instalasi | Satu installer .exe, tanpa instal Python terpisah, ukuran ≤ 1,5 GB | Instal di Windows 10 & 11 bersih |
| Offline | Seluruh fitur berjalan tanpa internet | Uji dengan jaringan dimatikan |

## 6. Risiko & Mitigasi

Risiko terbesar ada di driver sound card dan kualitas DeepFilterNet pada suara bernyanyi; keduanya diuji di Sprint 1 dan 2 sebelum UI dibangun.

| Risiko | Dampak | Mitigasi |
|---|---|---|
| SC202HD tidak punya ASIO resmi | Latensi lebih tinggi | WASAPI Exclusive + direct monitor fisik; latensi hanya memengaruhi playback dan dikompensasi otomatis |
| DeepFilterNet merusak nada panjang/vibrato | Vokal terdengar "berair" | Batas reduksi 12 dB, bisa dimatikan per track, uji dengan rekaman nyata di Sprint 2 |
| Fase/comb-filtering 2–4 penyanyi di satu mic | Suara tipis/berongga | Panduan posisi di layar: setengah lingkaran, jarak 35–45 cm simetris + EQ anti-boxiness |
| Bocor headphone ke mic | Piano/metronom terdengar di track vokal | Headphone closed-back wajib, volume headphone secukupnya; tanpa gate (gate merusak bagian lembut) |
| Nada meleset | Harmoni kurang rapi | Re-take per suara; pitch correction ditunda ke versi berikutnya |
| Callback audio Python tersendat | Klik/dropout | Buffer 256, thread audio terpisah, playback dari buffer yang sudah dimix sebelum rekam dimulai |
| Ukuran installer besar (PyTorch) | Unduh/instal lama | Pakai PyTorch versi CPU-only atau model ONNX; target ≤ 1,5 GB |

## 7. Arsitektur Teknis

Aplikasi dibangun dengan Python dalam tiga lapisan terpisah: engine audio real-time, engine pascaproduksi offline, dan antarmuka grafis.

| Lapisan | Teknologi | Tugas |
|---|---|---|
| Engine audio | `sounddevice` (PortAudio: ASIO/WASAPI), `soundfile`, `numpy` | Rekam, putar, metronom, kalibrasi latensi, tulis ke disk |
| Pascaproduksi | `pedalboard` (filter, EQ, kompresor, reverb konvolusi), DeepFilterNet, `pyloudnorm`, `scipy` | Rantai FR-5 s.d. FR-7, termasuk limiter true-peak 4× buatan sendiri |
| Pengukuran | `pyloudnorm` + modul true-peak/LRA sendiri, diverifikasi dengan FFmpeg `ebur128` | Angka laporan dan uji penerimaan |
| Ekspor | `soundfile` (WAV), FFmpeg + LAME (MP3) | File akhir dan tag |
| Antarmuka | PySide6 (Qt 6, lisensi LGPL) | 5 bilah track, VU meter, A/B, pengaturan |
| Paket | PyInstaller + Inno Setup | Installer .exe tunggal |

PySide6 dipilih menggantikan PyQt6 karena lisensi LGPL lebih aman jika aplikasi kelak dibagikan ke pihak lain.

Prinsip pemisahan: engine pascaproduksi bisa dijalankan dari baris perintah tanpa UI, sehingga bisa diuji dan disetel terpisah.

## 8. Rencana Pengembangan

Pengembangan berlangsung 10 minggu dalam 5 sprint; tiap sprint punya gerbang uji yang harus lulus sebelum lanjut.

| Sprint | Minggu | Cakupan | Gerbang lulus |
|---|---|---|---|
| 0 | 1 | Cek SC202HD (checklist Bagian 2), uji `sounddevice` + driver, kalibrasi latensi | Rekam-putar 48 kHz stabil 10 menit, latensi terukur |
| 1 | 2–3 | Engine audio via baris perintah: rekam 5 track, playback cue, metronom, kompensasi latensi, proyek & take | 5 track sejajar ≤ 3 ms, 0 dropout 60 menit |
| 2 | 4–5 | Engine pascaproduksi: FR-5 s.d. FR-8, laporan, uji DeepFilterNet pada rekaman nyata | Master memenuhi TP/LUFS, ≤ 60 detik |
| 3 | 6–8 | Antarmuka PySide6: 5 bilah, VU meter, slider, daftar take, preset ruang, A/B | Alur kerja Bagian 3 bisa dijalankan penuh lewat UI |
| 4 | 9–10 | Uji lapangan dengan paduan suara, perbaikan bug, installer .exe | Lulus seluruh kriteria Bagian 10 |

## 9. Protokol Kalibrasi & Gain Staging

Prosedur ini ditampilkan di aplikasi sebagai panduan langkah demi langkah sebelum sesi rekam pertama.

**Piano/Orgen**
- Volume keyboard di 70–80%, lalu atur gain input sound card.
- Target: rata-rata −18 s.d. −14 dBFS, puncak tidak melewati −6 dBFS (meter tetap hijau, sesekali kuning).

**Mikrofon vokal**
- Aktifkan phantom +48V, lalu minta kelompok menyanyikan bagian terkeras lagu.
- Target puncak −14 s.d. −10 dBFS, menyisakan ruang ≥ 10 dB sebelum clip.
- Gain jangan diubah di tengah sesi satu suara.

**Posisi penyanyi & headphone**
- 2–4 penyanyi membentuk setengah lingkaran, jarak 35–45 cm dari mic, sama rata untuk semua orang.
- Pop filter sekitar 7 cm di depan mic.
- Semua penyanyi aktif memakai headphone closed-back.
- Tombol direct monitor dinyalakan agar penyanyi mendengar suaranya sendiri dan musik dengan nyaman; volume headphone secukupnya agar tidak bocor ke mic.

## 10. Kriteria Penerimaan

Versi 1.1 dinyatakan siap rilis jika seluruh kriteria berikut lulus.

| Area | Kriteria lulus | Cara verifikasi |
|---|---|---|
| Standar YouTube | True Peak ≤ −1,0 dBTP pada 100% file uji; LUFS −14 ±1, atau lebih pelan dengan peringatan di laporan | FFmpeg `ebur128` sebagai pembanding independen |
| Stabilitas audio | 0 dropout selama 60 menit pada buffer 256 | Stress test |
| Sinkronisasi | Selisih antar-track ≤ 3 ms | Uji loopback klik |
| Kualitas vokal | Tidak ada artefak denoise yang jelas terdengar dan tidak ada comb-filtering akibat pemrosesan | Uji dengar oleh 2 orang + spektrogram |
| Kecepatan | Proses lagu 4 menit ≤ 60 detik di Core i5 | Benchmark |
| Ekspor | WAV 24-bit/48 kHz dan MP3 320 kbps valid, ekor reverb utuh, tidak ada file yang tertimpa | Validasi header + uji dengar akhir lagu |
| Kegunaan | Anggota paduan suara yang belum pernah memakai aplikasi bisa menyelesaikan 1 lagu dengan panduan di layar | Uji pengguna di Sprint 4 |

## 11. Di Luar Cakupan & Riwayat Versi

Fitur berikut sengaja tidak dikerjakan di v1.1 dan bisa dipertimbangkan untuk versi berikutnya:

- Koreksi nada (pitch correction) vokal kelompok.
- Punch-in (rekam ulang sebagian lagu saja).
- Lebih dari 1 mikrofon per suara atau merekam beberapa suara bersamaan.
- Plugin VST pihak ketiga.
- Sinkronisasi langsung dengan video.

| Versi | Tanggal | Perubahan |
|---|---|---|
| 1.1 rev. 1 | 07-11-2026 | Target sinkronisasi antar-track diubah dari ≤ 1 ms menjadi ≤ 3 ms (keputusan pemilik proyek). Uji SC202HD: driver USB generik (chip Realtek, tanpa ASIO) menggeser latensi 1–3 ms setiap stream dibuka dan tidak bisa dikoreksi otomatis. Selisih 3 ms setara jarak sekitar 1 m antar-penyanyi: tidak terdengar sebagai gema karena setiap suara dinyanyikan orang berbeda. Ditambah pemanasan sound card 5 detik sebelum hitungan awal |
| 1.1 | 06-11-2026 | Disesuaikan ke SPL Audio SC202HD; pitch correction dihapus; monitoring via direct monitor fisik; auto-balance + slider; prioritas mastering TP > LUFS > LRA; manajemen proyek; jadwal 10 minggu |
| 1.0 | 06-11-2026 | Draf awal |
