import ctypes

from kotoba_desktop.win32.input import (
    INPUT,
    KEYEVENTF_EXTENDEDKEY,
    KEYEVENTF_KEYUP,
    _pairs,
    _vk_input,
    utf16_units,
)


def test_input_struct_size() -> None:
    # 64 ビット版の INPUT は 40 バイト。ずれると SendInput が ERROR_INVALID_PARAMETER になる
    assert ctypes.sizeof(INPUT) == (40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)


def test_utf16_units_surrogate_pair() -> None:
    assert utf16_units("a𠮷") == [0x61, 0xD842, 0xDFB7]


def test_pairs_keep_surrogates_together() -> None:
    events = [
        (i.u.ki.wScan, bool(i.u.ki.dwFlags & KEYEVENTF_KEYUP))
        for i in _pairs([0x61, 0xD842, 0xDFB7])
    ]
    assert events == [
        (0x61, False),
        (0x61, True),
        (0xD842, False),
        (0xDFB7, False),
        (0xD842, True),
        (0xDFB7, True),
    ]


def test_insert_is_extended_key() -> None:
    assert _vk_input(0x2D, False).u.ki.dwFlags & KEYEVENTF_EXTENDEDKEY
    assert not _vk_input(ord("V"), False).u.ki.dwFlags & KEYEVENTF_EXTENDEDKEY
