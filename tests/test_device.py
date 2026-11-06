"""Tes pencarian perangkat (data tiruan, tanpa hardware)."""

from chorale.audio.device import DeviceInfo, find_io_pair, matches_keyword

W = "Windows WASAPI"


def _dev(i, name, api=W, i_ch=0, o_ch=0):
    return DeviceInfo(i, name, api, i_ch, o_ch, 48000.0)


FAKE = [
    _dev(0, "Microphone (Realtek(R) Audio)", i_ch=2),
    _dev(1, "Speakers (Realtek(R) Audio)", o_ch=2),
    _dev(2, "Line (SPL Audio SC202HD)", i_ch=2),
    _dev(3, "Speakers (SPL Audio SC202HD)", o_ch=2),
    _dev(4, "SPL Audio SC202HD", api="MME", i_ch=2),
]


def test_matches_keyword_case_insensitive():
    assert matches_keyword("Line (SPL Audio SC202HD)", "sc202")
    assert matches_keyword("SPL thing", ("SC202", "SPL"))
    assert not matches_keyword("Speakers (Realtek(R) Audio)", ("SC202", "SPL"))


def test_find_io_pair_within_hostapi():
    dev_in, dev_out = find_io_pair(W, "SC202", FAKE)
    assert dev_in.index == 2
    assert dev_out.index == 3


def test_find_io_pair_missing():
    assert find_io_pair(W, "Focusrite", FAKE) == (None, None)
