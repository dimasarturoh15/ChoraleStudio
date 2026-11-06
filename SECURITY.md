# Kebijakan keamanan

## Versi yang didukung

| Versi | Didukung |
|---|---|
| 1.1.x | ✅ |
| < 1.1 | ❌ |

## Ruang lingkup

HarmoniSATB Studio adalah aplikasi desktop yang sepenuhnya offline:

- Tidak ada kode jaringan; aplikasi tidak mengirim atau menerima data lewat internet.
- Data yang disimpan hanya pengaturan, hasil kalibrasi, daftar proyek terakhir, dan log di `%APPDATA%\HarmoniSATB\`, serta folder proyek yang dipilih pengguna.
- Installer berjalan per pengguna tanpa hak admin.
- FFmpeg dijalankan sebagai proses anak dengan argumen daftar (bukan string shell) dan hanya pada berkas yang dibuat aplikasi.

Contoh masalah yang relevan: berkas `proyek.json` yang dibuat khusus sehingga aplikasi menulis atau menghapus berkas di luar folder proyek, DLL yang dimuat dari lokasi yang tidak semestinya, atau log yang tanpa sengaja memuat data pribadi.

## Melaporkan kerentanan

Jangan laporkan kerentanan lewat Issue publik. Gunakan **[Report a vulnerability](https://github.com/dimasarturoh15/ChoraleStudio/security/advisories/new)** di tab Security repositori ini.

Sertakan versi aplikasi, versi Windows, langkah untuk memunculkan masalah, dan dampaknya. Laporan akan ditanggapi sebaik mungkin; proyek ini dikelola satu orang, jadi mohon kesabarannya.
