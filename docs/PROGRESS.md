# Progres HarmoniSATB Studio

Rujukan: [PRD_v1.1.md](PRD_v1.1.md). Daftar segmen di bawah adalah rancangan awal yang dipetakan dari Rencana Pengembangan PRD (Bagian 8) dan bisa disesuaikan.

| Segmen | Cakupan | Sprint PRD | Status |
|---|---|---|---|
| 0 | Fondasi proyek: CLAUDE.md, struktur folder, .venv, requirements, README | — | ✅ Selesai |
| 1 | Cek SC202HD & driver, uji rekam-putar 48 kHz via sounddevice (tools/) | 0 | 🔄 Sedang dikerjakan |
| 2 | Model proyek & take (FR-9), engine rekam/putar: perangkat, perekam ke disk, mixer monitoring, level meter | 1 | 🔄 Kode & tes selesai, demo SC202HD menunggu hardware |
| 3 | Metronom & count-in (FR-4), kompensasi latensi sinkron ≤ 1 ms (FR-3), CLI 5 track, stress test 60 menit | 1 | 🔄 Kode & tes selesai, uji SC202HD menunggu hardware |
| 4 | Pascaproduksi FR-5 & FR-6: HPF, EQ, kompresor, penyeimbang, panning, reverb | 2 | ✅ Selesai; DeepFilterNet ditunda (menunggu keputusan pengguna) |
| 5 | Mastering FR-7, pengukuran (LUFS/TP/LRA), ekspor & laporan FR-8, verifikasi ebur128 | 2 | ✅ Selesai (gerbang Sprint 2 lulus, dengan peredam derau dilewati) |
| 6 | UI PySide6: kerangka, tema, daftar proyek, proyek baru, pengaturan + kalibrasi | 3 | ✅ Selesai |
| 7 | UI: layar rekam 5 track, VU meter, transport, daftar take, panduan rekam, proses & hasil/A-B | 3 | Belum |
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
- ~~PortAudio bawaan sounddevice tanpa ASIO~~. Koreksi di Segmen 1: wheel sounddevice juga membawa `libportaudio64bit-asio.dll`, yang aktif dengan `SD_ENABLE_ASIO=1`.
- DeepFilterNet belum dipasang; akan dievaluasi di Segmen 4 (perhatikan ukuran installer ≤ 1,5 GB).

**Keputusan teknis**
- Versi paket dikunci (`==`) agar build bisa diulang.
- pytest memakai `pythonpath = ["src", "."]` di pyproject.toml, jadi tidak perlu `pip install -e .`.

---

## Segmen 1 — Uji hardware SC202HD (sedang dikerjakan)

**Yang sudah dikerjakan**
- `src/chorale/audio/devices.py` (di Segmen 2 diganti nama menjadi `device.py`): daftar host API & perangkat, pencarian pasangan input/output SC202HD per host API, konstanta 48 kHz / buffer 256. Mengaktifkan build PortAudio ber-ASIO (`SD_ENABLE_ASIO=1`).
- `src/chorale/audio/calibration.py`: sweep uji, deteksi jeda dengan cross-correlation (plus deteksi polaritas terbalik dan skor keyakinan), simpan/baca `%APPDATA%\HarmoniSATB\calibration.json`.
- Skrip `tools/list_devices.py`, `tools/test_wasapi.py`, `tools/calibrate_latency.py`, `tools/stress_test.py` (+ `tools/_common.py`). Semua menerima `--device <kata kunci>`, sehingga bisa diuji dengan perangkat lain.
- Tes: `tests/test_calibration.py`, `tests/test_devices.py`. Total 28 tes lulus.

**Uji coba skrip dengan sound card bawaan laptop (Realtek), sebagai pengganti sementara**
- `test_wasapi.py`: WASAPI Exclusive 48 kHz berhasil, input 1 dan 2 kanal, 24-bit diterima, rekam+putar 3 detik 0 dropout.
- `stress_test.py --minutes 1`: 0 dropout, beban callback rata-rata 5,2% (maks 8,1%).
- `calibrate_latency.py` belum dijalankan (butuh kabel loopback di SC202HD).

**Checklist PRD Bagian 2 (SC202HD)**

| Item | Hasil |
|---|---|
| Jumlah input terpisah di Windows | Belum diuji. SC202HD tidak terlihat oleh Windows. |
| Kenop direct monitor fisik | Menunggu pengecekan manual pengguna |
| Driver ASIO resmi | Build PortAudio ber-ASIO tersedia, tetapi **tidak ada driver ASIO terpasang** di Windows (registry `HKLM\SOFTWARE\ASIO` kosong). |
| Kunci 48 kHz / 24-bit | Belum diuji |
| Latensi terukur | Belum diuji |

**Masalah terbuka**
- SC202HD pernah dikenali Windows (`USB\VID_0BDA&PID_4E1F`, "SPL Audio SC202HD"), tetapi saat pengecekan statusnya *tidak tercolok*. Tidak muncul di daftar perangkat audio.
- VID 0BDA adalah chip USB Realtek, jadi kemungkinan besar SC202HD memakai driver USB Audio Class bawaan Windows. Karena itu ASIO resmi kemungkinan tidak ada, dan WASAPI Exclusive menjadi jalur utama (sesuai cadangan di PRD).

**Keputusan teknis**
- Semua stream memakai `latency="low"`. Bawaan sounddevice adalah `"high"`, yang membuat buffer efektif jauh lebih besar dari 256.
- Kalibrasi membuka stream baru di tiap percobaan, karena aplikasi juga membuka stream baru tiap kali mulai merekam. Dengan begitu konsistensi antar-pembukaan ikut teruji.

---

## Segmen 2 — Model proyek dan engine rekam/putar (kode & tes selesai, demo di SC202HD tertunda)

**Yang dikerjakan**
- `chorale/appdirs.py`: folder `%APPDATA%\HarmoniSATB` dan penulisan JSON atomik (file sementara, fsync, lalu ganti nama). Dipakai oleh proyek, recent.json, dan kalibrasi.
- `project/model.py`: `Project` (judul, tempo 40–240, birama 2/4·3/4·4/4·6/8, hitungan awal 0/1/2, metronom-setelah-count-in, tanggal dibuat/diubah), 5 `Track` tetap (piano stereo, vokal mono; take, take aktif, volume −12..+6 dB, solo, mute), `Take` (id, file, waktu, durasi, lengkap). Setiap perubahan lewat metode Project langsung disimpan. Aturan "vokal butuh piano dulu" ada di `can_record()`.
- `project/store.py`: buat proyek (folder `proyek.json`, `takes/`, `master/`; folder lama tidak pernah dipakai ulang), buka proyek, pemulihan take yatim, daftar proyek terakhir (maks. 10).
- Nama take: `<track>_take<N>_<YYYYMMDD-HHMMSS>.wav`. N diambil dari proyek **dan** isi folder takes/, dan file yang sudah ada tidak pernah ditimpa.
- `audio/device.py` (sebelumnya `devices.py`): pemilihan otomatis ASIO → WASAPI Exclusive → WASAPI Shared, stream duplex 48 kHz float32 latensi rendah, buffer 128/256/512/1024, pesan error ramah (tidak ditemukan, bukan 48 kHz beserta cara memperbaikinya, perangkat terputus).
- `audio/recorder.py`: ring buffer yang dialokasikan sekali, thread penulis WAV PCM 24-bit, header + flush tiap ≤ 1 detik, clip ke ±1.0 sebelum ditulis, cek ruang disk < 2 GB.
- `audio/player.py`: mixer (solo, mute, volume; track yang sedang direkam selalu dikecualikan) yang dibuat sebelum stream dimulai, dan pemutar yang di callback hanya menyalin data.
- `audio/meter.py`: puncak per blok (penahan puncak sampai dibaca UI), lampu clip yang tetap menyala sampai di-reset, zona warna FR-1.
- `audio/session.py`: satu sesi Putar/Rekam. Callback hanya berisi putar → meter → salin ke ring. Ada deteksi sound card tercabut (callback berhenti > 1 detik); take tetap disimpan dengan status *tidak lengkap*.
- `tools/demo_record.py`: proyek contoh di `projects/`, file uji piano sintetis, rekam N detik dengan hitung mundur dan meter teks.

**Hasil tes**: 83 tes lulus (`pytest`). Mencakup simpan/buka, take baru tidak menimpa, take aktif, pemulihan take yatim, recent.json, mixer solo/mute/volume/kecuali-track-rekam, meter dan clip, WAV 24-bit tepat sampai ke sampelnya, salinan file saat masih merekam (simulasi listrik padam), input berhenti mendadak, serta sesi lengkap dengan stream palsu (piano lalu bass, retake, perangkat dicabut).

**Uji demo di sound card bawaan laptop (Realtek, pengganti sementara)**: WASAPI Exclusive, rekam 4,00 detik mono 24-bit, 0 dropout, retake menjadi Take 2, proyek.json dan recent.json benar.

**Masalah terbuka**
- Demo dengan mic SC202HD belum dijalankan karena SC202HD masih belum terlihat oleh Windows (sama seperti Segmen 1).
- Segmen 1 dan 2 belum di-commit, karena syarat selesai keduanya butuh SC202HD.
- Monitoring memutar track mono di tengah dengan gain penuh di kedua kanal (tanpa pan law). Ini hanya untuk headphone; panning sebenarnya ada di FR-5.

**Keputusan teknis**
- Header WAV diperbarui eksplisit (`SFC_UPDATE_HEADER_NOW`) setiap flush. Terbukti, `flush()` saja membiarkan header mencatat 0 byte data. libsndfile memaafkan hal itu, tetapi FFmpeg/DAW bisa menganggap file kosong. Tes memeriksa header mentah.
- Solo: jika ada track yang di-solo, hanya track itu yang terdengar; mute selalu menang atas solo.
- Take hasil rekaman baru otomatis menjadi take aktif. Take yatim hasil pemulihan tidak dijadikan aktif.
- File take yang 0 frame (stream gagal sebelum ada audio) dihapus oleh sesi yang membuatnya, supaya tidak muncul sebagai take kosong.

---

## Segmen 3 — Metronom, kompensasi latensi, CLI 5 track (kode & tes selesai, uji SC202HD tertunda)

**Yang dikerjakan**
- `audio/metronome.py`: klik sintetis (ketukan 1 = 1760 Hz, lainnya 880 Hz, 30 ms), posisi ketukan k = `round(k × sampel_per_ketukan)` dihitung langsung dari k sehingga tidak bergeser, count-in 0/1/2 bar (ketukan negatif), opsi berhenti setelah count-in, volume sendiri (default −6 dB). Untuk 6/8, tempo dihitung per seperdelapan (6 klik per birama).
- `audio/session.py` sekarang punya garis waktu lagu: frame 0 = awal birama setelah count-in. Pemutar dan metronom berjalan dari −count-in, perekam baru menyimpan mulai 00:00. Klik hanya ditambahkan ke buffer output, jadi tidak mungkin masuk ke file rekaman (dites).
- Kompensasi latensi: dicari di `calibration.json` dengan kombinasi yang sama persis (perangkat input/output, host API, Exclusive/Shared, buffer, 48 kHz). Jika tidak ada, dipakai latensi laporan driver dan pengguna mendapat peringatan. Nilai yang dipakai dicatat di take (`latency_compensation`).
- Aturan rekam: vokal butuh take piano; vokal = 1 kanal mono; piano = stereo, atau mono dengan `--mono` / jika sound card hanya punya 1 input; take vokal < 90% durasi piano ditandai tidak lengkap.
- `tools/cli_session.py`: `buat`, `info`, `rekam <track>`, `putar`, `daftar-take`, `pilih-take`, `atur` (volume/solo/mute, dibutuhkan untuk menguji FR-2). Meter teks per input, tampilan hitungan awal, berhenti dengan Enter. Rekam vokal berhenti otomatis di akhir piano + 1 detik.
- `tools/sync_test.py`: piano merekam klik metronom lewat loopback, lalu 4 vokal merekam piano (di-solo) lewat loopback. Posisi klik tiap take diukur terhadap grid ketukan; lulus jika selisih antar-track ≤ 48 sampel (1 ms).
- `tools/stress_test.py` diganti agar memakai engine aplikasi (AudioSession: rekam WAV 24-bit lewat ring buffer + thread disk, sambil memutar). File uji ditaruh di folder sementara dan dihapus di akhir.
- `tests/conftest.py`: semua tes memakai %APPDATA% sementara, sehingga kalibrasi dan recent.json asli tidak tersentuh.

**Hasil tes**: 118 tes lulus. Tes baru:
- `test_metronome.py`: posisi klik identik dengan rumus untuk tempo 40/70/72/97/240 dan buffer 128/256/1024/333 (hasil tidak tergantung ukuran blok), tidak bergeser setelah 60 menit, panjang count-in, aksen, berhenti setelah count-in, volume.
- `test_sync.py`: **simulasi kabel loopback** (stream palsu yang mengembalikan output ke input dengan jeda 777 sampel). Hasil:
  - 5 track direkam berurutan, semua tepat di grid, selisih 0 sampel.
  - Kontrol tanpa kompensasi: piano telat 777 sampel, bass telat 1554 sampel. Ini membuktikan tesnya peka.
  - Klik metronom dan count-in tidak terekam.
  - Kalibrasi tersimpan benar-benar dipakai; tanpa kalibrasi muncul peringatan dan dipakai angka driver.
  - Aturan 90%.

**Uji hardware**
- Stress test engine 60 menit, buffer 256, WASAPI Exclusive, di Realtek (pengganti sementara), 15:10–16:10: **LULUS**.
  - 0 dropout dan 0 sampel hilang di ring buffer.
  - Beban callback rata-rata 7,7% (sempat 334% sesaat ketika CPU dipakai benchmark lain, tetapi tetap tanpa dropout).
  - CPU proses 1,4% dari total.
  - File 59,74 menit, 492 MB.
  - **Catatan:** file rekaman 15,6 detik (0,43%) lebih pendek dari waktu jam Windows, dan selisihnya bertambah merata. Kemungkinan jam audio Realtek berjalan sedikit berbeda dari jam Windows. Ini tidak memengaruhi kesejajaran antar-track (rekam dan putar berada di callback yang sama), tetapi harus dicek ulang di SC202HD.
- `sync_test.py` dan stress test di SC202HD: belum bisa, karena SC202HD tidak terlihat oleh Windows.

**Keputusan teknis**
- Latensi dikompensasi **saat merekam** (perekam baru mulai menyimpan di frame lagu L), bukan dengan menggeser file setelah selesai. Hasilnya sama persis, tetapi file di disk selalu sudah sejajar, tanpa langkah tulis ulang yang bisa gagal jika listrik padam. Akibatnya, take kehilangan L sampel di akhir (sekitar 10–20 ms), yang tidak berpengaruh.
- Count-in saat memutar (`putar`) tidak dipakai; saat merekam selalu dipakai sesuai pengaturan proyek.
- Uji sinkron memakai solo piano untuk track vokal, agar level klik lewat loopback tidak menumpuk dari track ke track.

---

## Segmen 4 — Rantai pascaproduksi (kode & tes selesai; DeepFilterNet belum diputuskan)

**Yang dikerjakan**
- `dsp/chain.py`: tahap 2 HPF Butterworth orde 2 (12 dB/okt) dengan cutoff piano 35 / bass 75 / tenor 75 / alto 90 / sopran 90 Hz. Tahap 3 EQ peak −2 dB @ 400 Hz, Q 1,0 (pedalboard). Tahap 4 kompresor 2,5:1, attack 25 ms, release 140 ms, dengan threshold otomatis dan reduksi maks 4 dB. Pengatur seluruh rantai punya callback progres `(tahap 1–7, persen keseluruhan)` dan pembatalan (`threading.Event` atau fungsi), serta laporan per track.
- `dsp/denoise.py`: pembungkus DeepFilterNet (tahap 1). Jika paket tidak ada, tahap dilewati dan dicatat di laporan. Bisa dimatikan per track (`Track.denoise`).
- `dsp/balance.py`: LUFS terintegrasi (pyloudnorm, BS.1770-4), vokal → −23, piano → −25, lalu ditambah offset slider.
- `dsp/stereo.py`: pan constant-power (tenor 25% L, sopran 12% L, bass 12% R, alto 25% R) dan lebar piano 65% (M/S). Piano yang direkam mono ditaruh di tengah.
- `dsp/reverb.py`: IR sintetis (derau L/R tak berkorelasi, low-pass 5 kHz, peluruhan −60 dB tepat pada waktu decay, pre-delay 32 ms, seed tetap, energi dinormalkan). Preset Gereja Kecil 1,6 s / Aula 2,0 s / Katedral 2,4 s.
- `dsp/mixdown.py`: jumlahkan track + bus reverb, panjang = lagu + ekor IR penuh.
- Model proyek: `room_preset`, `reverb_amount` (proyek), `denoise` (per track).
- `tools/make_demo_project.py` (proyek contoh SATB **sintetis**) dan `tools/process_project.py` (proyek → `master\<Judul>_<YYYYMMDD-HHMM>_Mixdown.wav`, 24-bit, tidak pernah menimpa).

**Nilai jumlah reverb** (porsi wet: keluaran = (1 − wet) × dry + wet × reverb):

| Pilihan | Wet |
|---|---|
| Sedikit | 12% |
| Normal | 20% (sesuai PRD) |
| Banyak | 30% |

**Hasil tes**: 159 tes lulus. Tes DSP yang dipakai:
- HPF −3 dB di cutoff, sekitar −12 dB satu oktaf di bawahnya, < −22 dB dua oktaf di bawahnya, 0 dB di passband.
- EQ −2 dB di 400 Hz.
- Kompresor: tidak pernah lebih dari 4 dB, termasuk pada lonjakan sesaat.
- Penyeimbang mencapai target ±0,5 LU di tiga level masukan.
- Rasio L/R pan sesuai rumus, dan loudness tetap sama setelah pan.
- Side piano tepat 65%.
- RT60 IR (metode Schroeder) dalam ±8% dari preset, IR deterministik, kiri-kanan tidak berkorelasi, redaman di atas 5 kHz.
- Ekor mixdown utuh, urutan tahap dan progres 0→100, pembatalan, aturan mute.

**Demo**: `projects\Contoh SATB` (sintetis, 26,7 s) → mixdown 29,1 s (ekor 2,4 s), −16,1 LUFS, puncak −2,2 dBFS, diproses dalam 2,6 s. Belum dimaster, jadi masih lebih pelan dari target −14 LUFS.

**Evaluasi DeepFilterNet** (4 track vokal × 4 menit, suara sintetis bervibrato + desis −50 dBFS; dijalankan di venv terpisah di folder sementara, bukan .venv proyek)

| Jalur | Bisa dipasang? | Waktu 4 track | Tambahan ukuran |
|---|---|---|---|
| Python 3.12 (stack proyek) | **Tidak**: `deepfilterlib` tidak punya wheel 3.12 Windows (perlu Rust) | – | – |
| Python 3.11 + PyTorch 2.0.1 CPU | Ya, tetapi harus turun versi Python | **144,5 s** saat CPU tidak sibuk (284 s saat CPU sibuk) | ±1,06 GB (torch 848 MB) + model 8 MB |
| `deep-filter.exe` 0.5.6 (Rust/ONNX) | Ya; hanya membaca WAV float/16-bit | 1.104 s (saat CPU sibuk) | 26 MB |

- Kualitas pada nada panjang bervibrato: desis di jeda turun sekitar 10 dB (sesuai batas 12 dB), dan posisi audio tepat (0 sampel). **Tetapi suara ikut dikecilkan 9–12 dB dan bentuk gelombangnya berubah banyak** (SI-SNR 33,6 → 4–9 dB; sopran 27,7 dB). Ini sesuai dengan risiko yang ditulis di PRD.
- Rekomendasi: **jangan ditambahkan ke requirements dulu.** Tahap 1 tetap opsional (dilewati dengan catatan di laporan). Diputuskan ulang setelah ada rekaman nyanyian asli dari SC202HD. Kandidat jika ternyata layak: `deep-filter.exe` sebagai mode lambat opsional.
- Efek samping uji: model DeepFilterNet (8 MB) terunduh ke `%LOCALAPPDATA%\DeepFilterNet` (belum dihapus).

**Keputusan teknis**
- Piano melewati tahap 2, **5**, 6, 7. Tabel FR-5 hanya menyebut 2, 6, 7, tetapi FR-6 menetapkan piano −25 LUFS, jadi tahap penyeimbang tetap dipakai.
- Kompresor dibuat sendiri (numpy), bukan `pedalboard.Compressor`, supaya batas reduksi 4 dB bisa dijamin dan diuji. Threshold = level persentil 99,5 bagian aktif − 4/(1 − 1/2,5) dB; reduksi juga dipotong keras di 4 dB. Tidak ada makeup gain, karena tahap 5 yang mengatur level.
- Reverb sebagai bus kirim tunggal: semua track yang sudah di-pan dijumlahkan, kiri dikonvolusi dengan IR kiri dan kanan dengan IR kanan (posisi suara sedikit tetap terasa di ekor).
- Mixdown mengikuti aturan solo/mute yang sama dengan monitoring. Track yang tidak ikut disebut di laporan.
- File mixdown dikecilkan seperlunya agar puncak ≤ −1 dBFS (hanya file dengar, bukan master).

---

## Segmen 5 — Mastering, pengukuran, ekspor (gerbang Sprint 2 lulus)

**Yang dikerjakan**
- `dsp/measure.py`:
  - LUFS terintegrasi lewat pyloudnorm (untuk laporan), plus `fast_integrated_lufs` (K-weighting float32, blok 400 ms) untuk pencarian gain. Selisih keduanya ≤ 0,05 LU.
  - True Peak dengan oversampling 4x polyphase. Filter Nyquist sinc-Kaiser 65 tap, fase identitas dilewati, 6 konvolusi berjalan paralel.
  - LRA EBU Tech 3342 buatan sendiri (short-term 3 s tiap 0,1 s, gerbang −70 / −20 LU, P95 − P10).
  - Verifikasi silang dengan FFmpeg `ebur128=peak=true`.
- `dsp/master.py`:
  - Kompresor bus 1,5:1, reduksi maks 2 dB (attack 30 ms, release 250 ms).
  - Gain dicari secara iteratif agar setelah limiter tercapai −14 LUFS.
  - Limiter true-peak buatan sendiri: kebutuhan gain per sampel dari puncak 4x, minimum bergeser (look-ahead 5 ms), release 100 ms, dihaluskan. Kurva gain dijamin ≤ kebutuhan (dites).
  - Ceiling −1,0 dBTP dengan margin 0,15 dB. Hasil diukur ulang; jika masih di atas ceiling, limiter diulang, lalu pengecilan statis sebagai pengaman terakhir.
  - Jika limiter perlu > 6 dB, gain diturunkan dan muncul peringatan. LRA hanya diukur.
  - `loudness_matched_gains` untuk A/B: yang lebih keras dikecilkan, tidak ada yang dikeraskan.
- `dsp/export.py`:
  - WAV PCM 24-bit dengan dither TPDF ±1 LSB (kuantisasi sendiri).
  - MP3 libmp3lame 320 kbps CBR dengan tag judul. MP3 hasil encode didekode lalu diukur True Peak-nya; jika > −1,0 dBTP, di-encode ulang sedikit lebih pelan.
  - Nama `<Judul>_<YYYYMMDD-HHMM>_Master.wav/.mp3` dan `_Laporan.txt`: spasi menjadi `_` seperti mockup, karakter terlarang Windows dibuang, dan nama dasar yang sama untuk ketiga file. Jika sudah ada, ditambah akhiran `-2`, `-3`, dan seterusnya.
  - Ekor: potong setelah sampel terakhir > −60 dBFS, lalu tambah 1 detik hening.
- `dsp/produce.py`: `produce(project, progress, cancel, export, verify)` menjalankan seluruh rantai. Progres dilaporkan dalam 7 langkah dengan teks persis seperti mockup Processing. Laporan .txt berbahasa Indonesia. MP3 dan verifikasi FFmpeg berjalan paralel.
- Percepatan: track dalam satu tahap rantai diproses paralel (thread).
- `tools/process_project.py` sekarang menghasilkan WAV + MP3 + laporan dan menampilkan isi laporan. `tools/benchmark.py` mengukur waktu proyek sintetis 5 × 4 menit. `tools/make_demo_project.py --birama N`.

**Hasil tes**: 192 tes lulus. Tes baru di `test_master.py`:
- Referensi −23 LUFS, LUFS cepat cocok dengan pyloudnorm.
- Ketepatan True Peak 5 frekuensi, puncak antar-sampel terdeteksi.
- LRA bertingkat 10 LU.
- Verifikasi silang FFmpeg pada 3 jenis sinyal.
- **TP ≤ −1,0 dBTP pada 7 sinyal**: musik, transien keras, gelombang kotak, sinus 12 kHz antar-sampel, sweep, ledakan tiba-tiba, derau putih keras.
- −14 ±0,2 LUFS pada materi normal; peringatan muncul pada materi sangat dinamis.
- A/B sama kelantangannya.
- Nama file dan anti-timpa.
- Ekor −60 dB + 1 detik.
- Dither TPDF, WAV 24-bit valid.
- MP3: 320 kb/s, 48 kHz, tag judul, TP ≤ −1,0.
- `produce()` ujung ke ujung, termasuk progres, laporan, ekor reverb, pembatalan tanpa meninggalkan file.

**Gerbang Sprint 2**

| Kriteria | Hasil |
|---|---|
| True Peak ≤ −1,0 dBTP | Contoh SATB: −1,15 dBTP (FFmpeg −1,1), MP3 −1,1 |
| −14 LUFS ±1 | −14,1 LUFS (FFmpeg −14,0) |
| `produce()` ≤ 60 detik untuk lagu 4 menit | **33,8 detik** (5 track × 4 menit sintetis, 16 inti logis; rantai 11 s, mastering + ekspor 23 s). Tanpa peredam derau. |
| Proyek contoh lewat `process_project.py` | WAV + MP3 + laporan di `projects\Contoh SATB\master\`, status "Siap YouTube" |

**Keputusan teknis**
- Verifikasi silang FFmpeg: selisih ≤ 0,07 dB pada musik dan derau. **Pada sinus murni frekuensi sangat tinggi** (12 kHz dengan puncak di antara dua sampel), FFmpeg terlalu tinggi sekitar 0,6 dB dari nilai sebenarnya, sedangkan pengukuran kita meleset 0,1 dB atau kurang. Kasus seperti itu tidak dijadikan syarat lulus.
- Oversampler kita sedikit melebih-lebihkan puncak pada frekuensi di atas 10 kHz (maks +0,25 dB pada 16 kHz). Arahnya aman: limiter sedikit lebih hati-hati.
- Margin limiter 0,15 dB. Dengan margin 0,05 dB, FFmpeg membaca tepat −1,0 dBTP, jadi margin diperbesar agar meter lain juga membaca di bawah batas.
- Nilai LUFS di laporan dari pyloudnorm, sesuai permintaan. Versi cepat hanya untuk iterasi pencarian gain.
- Mixdown "Mentah" untuk A/B = hasil rantai Segmen 4 sebelum mastering, dipotong ekornya dengan aturan yang sama.
- Status laporan "Siap YouTube" = TP ≤ −1,0 dan LUFS dalam −14 ±1.

---

## Segmen 6 — Kerangka UI, daftar proyek, pengaturan (selesai)

**Yang dikerjakan**
- `ui/theme.py` + `ui/style.qss`: token warna dan warna track sesuai mockup, radius 4/6/8, teks minimal 13 px. Font Inter 3.19 (OTF) dan JetBrains Mono 2.304 (TTF) beserta lisensi OFL ada di `ui/fonts/` (diunduh dari jsDelivr karena github.com sedang tidak terjangkau). Cadangan: Segoe UI / Consolas.
- `ui/icons.py`: ikon garis buatan sendiri (SVG, dirender QtSvg, tajam di HiDPI).
- `ui/widgets.py`: kontrol bersegmen (dengan sublabel "Tidak tersedia"), sakelar, stepper tempo, 5 titik status, meter level dengan skala −42/−12/0 dB, bilah atas.
- `ui/main_window.py`: 1440×900, minimal 1280×800, QStackedWidget (Daftar Proyek, Pengaturan, layar proyek sementara).
- `ui/project_list.py`: data dari recent.json lewat `store.read_summary` (hanya membaca proyek.json, tanpa memulihkan atau menyimpan apa pun). Tanggal = waktu terakhir proyek diubah. "Buka Proyek Lain…" memakai dialog pilih folder.
- `ui/new_project.py`: lapisan modal di atas jendela (latar digelapkan, seperti mockup). Validasi judul tidak kosong; tempo dibatasi 40–240 (ketik 300 → 240). Folder default `Documents\HarmoniSATB\<judul>` (Documents dicari lewat Windows, jadi ikut jika dipindah ke OneDrive) dan bisa diganti lewat "Ubah…".
- `ui/settings_screen.py`:
  - Navigasi samping (Perangkat Audio / Tentang Aplikasi).
  - Pilihan sound card, mode driver (ASIO nonaktif + "Tidak tersedia" jika tidak ada), Sample Rate 48.000 Hz dan Bit Depth 24-bit terkunci, ukuran buffer.
  - Pemetaan input dengan meter live (`audio/monitor.py`, 30 fps lewat QTimer).
  - Kalibrasi latensi di QThread, dengan dialog konfirmasi keselamatan, progres "Mengukur… n/5", dan hasil "12.4 ms ✓ Akurat · Terakhir dikalibrasi …".
  - Simpan/Batal.
- `chorale/settings.py`: `%APPDATA%\HarmoniSATB\settings.json` (perangkat, mode driver, buffer, pemetaan input, folder proyek).
- `audio/device.py`: `list_sound_cards()` (gabungan input/output per kartu) dan `select_device(..., mode=)`.
- Logika kalibrasi dipindah ke `audio/calibration.py` (`measure_latency`, `accuracy_label`, `SAFETY_STEPS`). `tools/calibrate_latency.py` kini memakainya.
- `python -m chorale` (paket dipasang editable: `pip install -e .`). `tools/ui_screenshots.py` membuat screenshot dengan data contoh di folder sementara.

**Hasil tes**: 206 tes lulus. `tests/test_ui.py` (Qt offscreen, tanpa sound card) menguji:
- Daftar sound card dan mode paksa, pengaturan simpan/baca/validasi.
- `read_summary` tidak mengubah proyek.
- Kalibrasi lewat loopback palsu (700 sampel, selisih 1 → "Akurat").
- Font dan token QSS.
- Daftar proyek (isi dan kosong).
- Proyek baru (validasi, batas tempo, nilai tersimpan, teks persis mockup).
- Pengaturan (ASIO "Tidak tersedia", simpan, tampilan hasil kalibrasi).
- Navigasi jendela utama.

Aplikasi dijalankan sungguhan (`python -m chorale`) dan tertutup normal.

**Screenshot**: `docs/screenshots/01`–`07` (1440×900 dan 1280×800, layar 175%).

**Perbandingan dengan mockup**

| Bagian | Perbedaan | Alasan |
|---|---|---|
| Skala meter, sublabel "Tidak tersedia" | 13 px (mockup 10–11 px) | Aturan teks minimal 13 px |
| Meter level | Lebar 180 px (mockup 110 px) | Label 13 px tidak muat di 110 px tanpa bertumpuk |
| Nama perangkat | Nama dari Windows, mis. "Realtek(R) Audio"; SC202HD akan tampil "SPL Audio SC202HD" (tanpa "(USB)") | Belum ada SC202HD tersambung; nama diambil apa adanya dari driver |
| Kalibrasi | Menampilkan "— Belum dikalibrasi" | Belum ada kalibrasi untuk perangkat ini (mockup memakai contoh 12.4 ms) |
| Teks tambahan | "Disimpan di … Ubah…" (Proyek Baru), "Judul lagu tidak boleh kosong.", "Belum ada proyek…", dialog keselamatan sebelum kalibrasi, pesan error perangkat, isi halaman Tentang Aplikasi | Diminta (folder bisa diganti) atau dibutuhkan untuk keadaan yang tidak ada di mockup |
| Ikon | Digambar sendiri, bentuk sedikit berbeda | Menghindari masalah lisensi ikon |
| Membuka proyek | Layar sementara | Layar rekam 5 track = Segmen 7 |
| Jarak vertikal Pengaturan | Sedikit lebih rapat dari mockup | Agar Batal/Simpan muat di 900 px tanpa scroll |
| Cacat mockup | Tidak ditiru: judul "Bapa Engkau Sungguh Baik" utuh, tidak ada teks terpotong di 1280×800 | Aturan CLAUDE.md |

**Masalah terbuka**
- Path yang sangat panjang di "Disimpan di …" dipendekkan di tengah dengan "…" (path lengkap ada di tooltip). Path di bawah Documents tampil pendek ("Documents\HarmoniSATB\<judul>").
- FFmpeg dari imageio-ffmpeg adalah build GPL. Ini perlu diperhatikan saat membuat installer (Segmen 9).
- Meter Pengaturan membuka input sound card secara eksklusif selama layar Pengaturan terbuka, dan ditutup otomatis saat keluar atau saat kalibrasi.

**Keputusan teknis**
- Dialog Proyek Baru dibuat sebagai lapisan di dalam jendela, bukan jendela terpisah, agar latar digelapkan persis seperti mockup.
- Ukuran font diatur lewat QSS (`role`), karena `setFont` kalah oleh aturan QSS global.
- Jarak ikon-teks pada tombol dibuat dengan dua spasi di depan teks (QSS Qt tidak punya pengaturan jarak ikon).
- Mode driver disimpan hanya jika pengguna mengubahnya; selain itu tetap otomatis (ASIO → WASAPI Exclusive → Shared).
