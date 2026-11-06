"""Tahap 1 (opsional): peredam derau DeepFilterNet.

Paket DeepFilterNet tidak wajib. Jika tidak terpasang, available() bernilai
False dan rantai pascaproduksi melewati tahap ini dengan catatan di laporan.
"""

from __future__ import annotations

import numpy as np

MAX_ATTENUATION_DB = 12.0
MSG_UNAVAILABLE = "Peredam derau dilewati: paket DeepFilterNet belum terpasang."

_model = None


def available() -> bool:
    try:
        import df.enhance  # noqa: F401
    except Exception:  # noqa: BLE001 - ImportError atau error torch saat import
        return False
    return True


def denoise(audio: np.ndarray, samplerate: int = 48000,
            max_attenuation_db: float = MAX_ATTENUATION_DB) -> np.ndarray:
    """Kurangi derau pada audio mono (frames,) dengan reduksi maksimal 12 dB."""
    global _model
    import torch
    from df.enhance import enhance, init_df

    if _model is None:
        _model = init_df(log_level="ERROR")
    model, state, _ = _model
    if samplerate != state.sr():
        raise ValueError(f"DeepFilterNet butuh {state.sr()} Hz")
    tensor = torch.from_numpy(np.ascontiguousarray(audio, dtype=np.float32))[None, :]
    out = enhance(model, state, tensor, atten_lim_db=max_attenuation_db)
    return out[0].numpy().astype(np.float32)
