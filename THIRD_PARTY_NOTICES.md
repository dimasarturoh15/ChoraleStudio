# Komponen pihak ketiga

HarmoniSATB Studio memakai komponen open-source berikut. Hak cipta setiap komponen tetap milik pemiliknya masing-masing. Teks lisensi lengkapnya disertakan di folder `licenses\` hasil instalasi (dikumpulkan oleh `tools/build_installer.py`) dan dapat dibuka dari **Pengaturan > Tentang Aplikasi > Buka Folder Lisensi**.

## Ikut dalam aplikasi yang dipasang

| Komponen | Versi | Lisensi | Dipakai untuk | Sumber |
|---|---|---|---|---|
| Qt for Python (PySide6, shiboken6) | 6.12.0 | LGPL v3 | Antarmuka | https://www.qt.io/qt-for-python |
| PortAudio | V19.7.0 | MIT | Audio masuk dan keluar (ASIO, WASAPI) | https://www.portaudio.com |
| sounddevice | 0.5.6 | MIT | Pembungkus PortAudio | https://github.com/spatialaudio/python-sounddevice |
| libsndfile | 1.2.2 | LGPL v2.1 | Membaca dan menulis WAV | https://github.com/libsndfile/libsndfile |
| soundfile | 0.14.0 | BSD 3-Clause | Pembungkus libsndfile | https://github.com/bastibe/python-soundfile |
| NumPy | 2.5.4 | BSD 3-Clause | Perhitungan audio | https://numpy.org |
| SciPy | 1.18.1 | BSD 3-Clause | Filter, korelasi, reverb | https://scipy.org |
| pedalboard (memakai JUCE) | 0.9.26 | GPL v3 | EQ dan efek | https://github.com/spotify/pedalboard |
| pyloudnorm | 0.2.0 | MIT | Pengukuran LUFS | https://github.com/csteinmetz1/pyloudnorm |
| FFmpeg (build "essentials" gyan.dev) | 9.0.2 | GPL v3 | Encoding MP3 (LAME) dan verifikasi `ebur128` | https://ffmpeg.org · https://www.gyan.dev/ffmpeg/builds/ |
| imageio-ffmpeg | 0.8.1 | BSD 2-Clause | Menyertakan biner FFmpeg | https://github.com/imageio/imageio-ffmpeg |
| cffi, pycparser | - | MIT, BSD 3-Clause | Dependensi sounddevice dan soundfile | https://cffi.readthedocs.io |
| Font Inter | - | SIL OFL 1.1 | Huruf antarmuka | https://rsms.me/inter/ |
| Font JetBrains Mono | - | SIL OFL 1.1 | Huruf angka | https://www.jetbrains.com/lp/mono/ |
| Python | 3.12 | PSF License | Runtime | https://www.python.org |

## Hanya untuk pengembangan dan build

| Komponen | Versi | Lisensi | Dipakai untuk |
|---|---|---|---|
| pytest | 9.2.0 | MIT | Tes |
| PyInstaller | 6.22.3 | GPL v2 dengan pengecualian bootloader | Membuat aplikasi tanpa Python; pengecualian ini membolehkan aplikasi hasil build memakai lisensi apa pun |
| Inno Setup | 6 | Lisensi Inno Setup | Membuat Setup.exe |

## Catatan GPL

pedalboard dan build FFmpeg yang disertakan berlisensi **GNU General Public License v3**. Konsekuensinya, bila installer HarmoniSATB Studio dibagikan kepada pihak lain, penerima berhak memperoleh kode sumber komponen tersebut dan aplikasi yang memakainya, sesuai ketentuan GPL v3. Kode sumber FFmpeg tersedia di https://ffmpeg.org/download.html dan pedalboard di https://github.com/spotify/pedalboard.

## Data uji

[Choral Singing Dataset](https://zenodo.org/record/2649950) (Universitat Pompeu Fabra, CC BY-NC 4.0) dipakai di luar repositori sebagai bahan uji rekaman paduan suara asli. Berkas audionya tidak disertakan di repositori maupun di aplikasi.
