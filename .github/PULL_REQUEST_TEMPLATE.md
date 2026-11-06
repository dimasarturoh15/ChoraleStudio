## Ringkasan

<!-- Apa yang diubah dan mengapa. Tautkan Issue bila ada, misalnya "Menutup #12". -->

## Jenis perubahan

- [ ] Perbaikan bug
- [ ] Keandalan atau performa
- [ ] Antarmuka
- [ ] Dokumentasi
- [ ] Lainnya:

## Hasil uji

- [ ] `pytest -q` lulus (tulis jumlah tes)
- [ ] Tes regresi ditambahkan untuk perbaikan bug
- [ ] `tools/benchmark.py` (bila menyentuh DSP): ... detik
- [ ] `tools/stress_test.py` (bila menyentuh engine real-time): ... menit, ... dropout, sound card ...
- [ ] Tangkapan layar sebelum dan sesudah (bila menyentuh antarmuka)

## Pemeriksaan

- [ ] Sesuai cakupan PRD; tidak menambah fitur di luar PRD
- [ ] Callback audio tetap tanpa alokasi besar, I/O disk, logging, atau Qt
- [ ] Teks antarmuka dalam Bahasa Indonesia dan tampil utuh di 1280 × 800
- [ ] Tidak ada berkas audio, `.venv`, `build/`, `dist/`, atau model AI
- [ ] CHANGELOG.md diperbarui di bagian *Belum dirilis*
