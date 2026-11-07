# Uji Lapangan HarmoniSATB Studio

Panduan ini dipakai saat mencoba aplikasi bersama paduan suara sungguhan. Isinya mengikuti **Kriteria Penerimaan** di PRD (bagian 10). Aplikasi dianggap siap dipakai jika semua uji di bawah **Lulus**.

Cetak dokumen ini, atau isi langsung di komputer. Setiap uji punya kolom **Hasil** (tulis apa yang terjadi) dan **Lulus / Gagal** (coret salah satu).

---

## Sebelum mulai

**Perkiraan waktu:** 2–3 jam (termasuk istirahat).

**Orang yang dibutuhkan**
- 1 **teknisi**: orang yang memasang alat dan menjalankan uji teknis.
- 1 **pengamat**: mencatat jalannya uji kegunaan, **tidak boleh membantu** kecuali diminta.
- 1 **pengguna baru**: anggota paduan suara yang **belum pernah** memakai aplikasi ini.
- 4 kelompok penyanyi (Sopran, Alto, Tenor, Bass), masing-masing 2–4 orang, dan 1 pemain piano/orgen.
- 2 **pendengar penilai** untuk uji kualitas suara.

**Alat yang disiapkan**

| Alat | Sudah siap? |
|---|---|
| Laptop Windows 10/11 dengan HarmoniSATB Studio terpasang | ☐ |
| Sound card SPL Audio SC202HD + kabel USB | ☐ |
| Mikrofon condenser + kabel XLR + pop filter | ☐ |
| Headphone closed-back (1 per penyanyi) + splitter/ampli headphone | ☐ |
| Keyboard/piano digital + kabel ke sound card | ☐ |
| Kabel loopback: dari Output sound card ke Input 1 (untuk kalibrasi & uji sinkron) | ☐ |
| Lagu uji ± 4 menit yang sudah dikuasai semua suara | ☐ |
| Charger laptop **tercolok** (jangan memakai baterai saat merekam) | ☐ |
| Aplikasi pengolah suara Windows **dimatikan** (FxSound, Nahimic, Dolby, dan sejenisnya; tutup dari ikon pojok kanan bawah) | ☐ |
| **USB selective suspend** dimatikan (Control Panel → Power Options → Edit power plan → Change advanced power settings → USB settings → Disabled) | ☐ |
| SC202HD dicolok **langsung** ke port USB laptop, bukan lewat hub | ☐ |

**Catatan umum**

| Isian | Jawaban |
|---|---|
| Tanggal & tempat | |
| Laptop (merek, prosesor, RAM) | |
| Versi aplikasi (Pengaturan → Tentang Aplikasi) | |
| Nama teknisi / pengamat | |

---

## Uji 1 — Persiapan sound card dan kalibrasi latensi

*Dikerjakan teknisi, sekali per laptop.*

| Langkah | Yang dicatat | Hasil | Lulus / Gagal |
|---|---|---|---|
| 1. Colok SC202HD, buka aplikasi → **Pengaturan**. | Nama sound card yang muncul di "Perangkat". | | Lulus / Gagal |
| 2. Lihat **Mode Driver**. | Mode yang terpilih (ASIO / WASAPI Exclusive / Shared). | | — |
| 3. Kecilkan headphone, **matikan +48V**, pasang kabel loopback, lalu tekan **Mulai Kalibrasi**. | Angka "Latensi terukur" dan tulisan di sebelahnya (Akurat / Cukup / Tidak konsisten). | | Lulus jika **Akurat** atau **Cukup** |
| 4. Lepas kabel loopback, tekan **Simpan**. | — | | — |

---

## Uji 2 — Sinkronisasi antar-track (selisih ≤ 3 ms)

*Dikerjakan teknisi lewat terminal, dengan kabel loopback masih terpasang.*

| Langkah | Yang dicatat | Hasil | Lulus / Gagal |
|---|---|---|---|
| Jalankan `tools\sync_test.py` (lihat README). Aplikasi merekam 5 track klik lewat kabel loopback. | "Selisih terbesar antar-track" (ms). | ____ ms | Lulus jika **≤ 3 ms** |

---

## Uji 3 — Stabilitas audio (0 putus-putus selama 60 menit)

*Dikerjakan teknisi, bisa sambil istirahat.*

| Langkah | Yang dicatat | Hasil | Lulus / Gagal |
|---|---|---|---|
| Jalankan `tools\stress_test.py --minutes 60` (sound card SC202HD, buffer 256). | "TOTAL DROPOUT". | ____ | Lulus jika **0** |
| Dengan kabel loopback terpasang (phantom dan direct monitor mati), jalankan `tools\stress_test.py --minutes 60 --loopback`. | "LOMPATAN" dan menit kejadiannya. Lompatan adalah pergeseran waktu yang tidak terhitung sebagai dropout; penyanyi bisa mendengar klik kecil. | ____ | Catat saja (temuan SC202HD) |
| Perhatikan apakah laptop melambat atau kipas sangat bising. | Catatan bebas. | | — |

---

## Uji 4 — Kegunaan: pengguna baru menyelesaikan 1 lagu

*Ini uji terpenting. Pengguna baru memakai aplikasi sendiri dengan mengikuti petunjuk di layar. Pengamat hanya mencatat.*

Berikan satu kalimat ini kepada pengguna baru: **"Rekam lagu ini dengan aplikasi, lalu buat file untuk YouTube."** Mulai stopwatch.

| Langkah yang diharapkan | Berhasil sendiri? | Butuh bantuan? Di mana? | Waktu |
|---|---|---|---|
| 1. Membuat **Proyek Baru** (judul, tempo, birama). | Ya / Tidak | | |
| 2. Merekam **Piano/Orgen**. | Ya / Tidak | | |
| 3. Mengikuti **Persiapan Rekam Vokal** (posisi penyanyi, gain mic sampai "Level sudah pas", headphone). | Ya / Tidak | | |
| 4. Merekam **Bass, Tenor, Alto, Sopran** (boleh dengan take ulang). | Ya / Tidak | | |
| 5. Memilih take terbaik di daftar take. | Ya / Tidak | | |
| 6. Menekan **Proses Produksi & Master**. | Ya / Tidak | | |
| 7. Membandingkan **A · Mentah** dan **B · Master**. | Ya / Tidak | | |
| 8. Menemukan file hasil lewat **Buka Folder Hasil**. | Ya / Tidak | | |

**Lulus jika** pengguna baru menyelesaikan langkah 1–8 tanpa diajari (boleh bertanya ≤ 2 kali).

Hasil: ________ Lulus / Gagal

Catat juga kalimat atau tombol yang membingungkan, dengan kata-kata pengguna sendiri:

> ...

---

## Uji 5 — Kualitas suara vokal

*Dua pendengar menilai master WAV dengan headphone yang baik, masing-masing sendiri-sendiri.*

| Pertanyaan | Pendengar 1 | Pendengar 2 |
|---|---|---|
| Apakah ada bunyi aneh seperti "berair", "berdesis", atau suara terpotong-potong? | Ya / Tidak | Ya / Tidak |
| Apakah suara terdengar "tipis", "berongga", atau seperti dalam pipa (comb-filtering)? | Ya / Tidak | Ya / Tidak |
| Apakah keempat suara seimbang (tidak ada yang tenggelam)? | Ya / Tidak | Ya / Tidak |
| Apakah gema ruangan (reverb) terasa wajar? | Ya / Tidak | Ya / Tidak |

**Lulus jika** kedua pendengar menjawab **Tidak** pada dua pertanyaan pertama.
(Opsional untuk teknisi: periksa spektrogram file WAV, misalnya dengan Audacity, untuk melihat garis-garis aneh.)

Hasil: ________ Lulus / Gagal

---

## Uji 6 — Standar YouTube

*Dilihat di layar Hasil Produksi dan di file `…_Laporan.txt`.*

| Yang dicatat | Hasil | Lulus jika | Lulus / Gagal |
|---|---|---|---|
| Kelantangan (LUFS) | | −15 s.d. −13 LUFS, **atau** lebih pelan dengan peringatan kuning di laporan | Lulus / Gagal |
| Puncak (True Peak) | | **≤ −1,0 dBTP** | Lulus / Gagal |
| "Verifikasi independen (FFmpeg)" di laporan | cocok / berbeda | **cocok** | Lulus / Gagal |

---

## Uji 7 — Kecepatan proses

| Yang dicatat | Hasil | Lulus jika | Lulus / Gagal |
|---|---|---|---|
| "Waktu proses" di laporan, untuk lagu ± 4 menit | ____ detik | **≤ 60 detik** | Lulus / Gagal |

---

## Uji 8 — Ekspor

| Langkah | Yang dicatat | Lulus / Gagal |
|---|---|---|
| Buka folder hasil. Ada 3 file: `…_Master.wav`, `…_Master.mp3`, `…_Laporan.txt`? | Ya / Tidak | Lulus / Gagal |
| Putar WAV dan MP3 di pemutar musik biasa. Keduanya bisa diputar? | Ya / Tidak | Lulus / Gagal |
| Dengarkan 10 detik terakhir. Gema (reverb) habis dengan halus, tidak terpotong tiba-tiba? | Ya / Tidak | Lulus / Gagal |
| Tekan **Proses Ulang**. File lama tetap ada dan muncul 3 file baru? | Ya / Tidak | Lulus / Gagal |

---

## Uji 9 — Keamanan rekaman (sound card dicabut)

| Langkah | Yang dicatat | Lulus / Gagal |
|---|---|---|
| Saat merekam satu suara, **cabut kabel USB** sound card setelah ± 30 detik. | Muncul pesan "Sound card terputus" dengan detik yang tersimpan? | Lulus / Gagal |
| Colok lagi, tekan **Hubungkan Ulang**. | Aplikasi tersambung kembali? | Lulus / Gagal |
| Buka daftar take suara tadi. | Take tersimpan (bertanda "Tidak lengkap") dan bisa diputar sampai detik yang disebut? | Lulus / Gagal |

---

## Uji 10 — Instalasi dan tanpa internet

| Langkah | Yang dicatat | Lulus / Gagal |
|---|---|---|
| Pasang `HarmoniSATB-Studio-…-Setup.exe` di laptop lain yang **belum pernah** dipasangi Python. | Instalasi selesai, ada shortcut di Start Menu & Desktop? | Lulus / Gagal |
| Matikan Wi-Fi/internet, lalu ulangi rekam singkat + Proses Produksi. | Semua berjalan tanpa internet? | Lulus / Gagal |
| Ukuran file Setup.exe. | ____ MB (lulus jika ≤ 1,5 GB) | Lulus / Gagal |

---

## Ringkasan

| Kriteria PRD | Uji | Lulus / Gagal |
|---|---|---|
| Standar YouTube | 6 | |
| Stabilitas audio | 3 | |
| Sinkronisasi | 2 | |
| Kualitas vokal | 5 | |
| Kecepatan | 7 | |
| Ekspor | 8 | |
| Kegunaan | 4 | |
| Keamanan rekaman (NFR) | 9 | |
| Instalasi & offline (NFR) | 10 | |

**Jika ada yang gagal:** buka Pengaturan → Tentang Aplikasi → **Buka Folder Log**, salin isi folder itu, lalu kirimkan bersama catatan di dokumen ini kepada pengembang.
