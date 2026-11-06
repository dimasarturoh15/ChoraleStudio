"""Pengaturan bersama pytest."""

import pytest


@pytest.fixture(autouse=True)
def isolated_appdata(tmp_path, monkeypatch):
    """Arahkan %APPDATA% ke folder sementara agar tes tidak menyentuh kalibrasi/recent asli."""
    appdata = tmp_path / "appdata"
    monkeypatch.setenv("APPDATA", str(appdata))
    return appdata
