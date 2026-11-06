"""Konstanta produksi yang ringan (tanpa scipy/pedalboard) agar UI cepat terbuka.

Modul DSP yang berat baru dimuat saat proses produksi benar-benar dijalankan.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RoomPreset:
    label: str
    decay_s: float  # RT60: waktu ekor turun 60 dB


ROOM_PRESETS = {
    "gereja_kecil": RoomPreset("Gereja Kecil", 1.6),
    "aula": RoomPreset("Aula", 2.0),
    "katedral": RoomPreset("Katedral", 2.4),
}
DEFAULT_ROOM = "katedral"

# Porsi wet pada campuran akhir: keluaran = (1 - wet) * dry + wet * reverb.
REVERB_AMOUNTS = {"sedikit": 0.12, "normal": 0.20, "banyak": 0.30}
REVERB_AMOUNT_LABELS = {"sedikit": "Sedikit", "normal": "Normal", "banyak": "Banyak"}
DEFAULT_AMOUNT = "normal"

# Mastering (PRD FR-7)
TARGET_LUFS = -14.0
LUFS_TOLERANCE = 1.0
CEILING_DBTP = -1.0

# 7 langkah layar "Memproses Produksi"
STEP_LABELS = {
    1: "Membersihkan derau",
    2: "Menyaring frekuensi rendah",
    3: "Merapikan karakter suara",
    4: "Menyeimbangkan volume antar-suara",
    5: "Menata posisi stereo",
    6: "Menambahkan ruang (reverb)",
    7: "Mastering standar YouTube",
}
