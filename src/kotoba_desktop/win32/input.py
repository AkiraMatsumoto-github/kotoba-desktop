"""SendInput によるキー送信と、修飾キーの押下状態の取得。"""

import ctypes
from ctypes import wintypes

from kotoba_desktop.keys import EXTENDED_VK, MODIFIER_VK, Chord

user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
MAPVK_VK_TO_VSC = 0

# GetAsyncKeyState で見る修飾キー（左右の区別も含む）
_MODIFIER_STATE_VK = (0x10, 0x11, 0x12, 0x5B, 0x5C)  # Shift, Ctrl, Alt, 左 Win, 右 Win


class MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    )


class KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    )


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = (
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    )


class _INPUTUNION(ctypes.Union):
    _fields_ = (("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT))


class INPUT(ctypes.Structure):
    _fields_ = (("type", wintypes.DWORD), ("u", _INPUTUNION))


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT
user32.MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
user32.MapVirtualKeyW.restype = wintypes.UINT
user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
user32.GetAsyncKeyState.restype = wintypes.SHORT


def _vk_input(vk: int, up: bool) -> INPUT:
    flags = KEYEVENTF_KEYUP if up else 0
    if vk in EXTENDED_VK:
        flags |= KEYEVENTF_EXTENDEDKEY
    scan = user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)
    return INPUT(INPUT_KEYBOARD, _INPUTUNION(ki=KEYBDINPUT(vk, scan, flags, 0, 0)))


def _unicode_input(code_unit: int, up: bool) -> INPUT:
    flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if up else 0)
    return INPUT(INPUT_KEYBOARD, _INPUTUNION(ki=KEYBDINPUT(0, code_unit, flags, 0, 0)))


def _send(inputs: list[INPUT]) -> None:
    array = (INPUT * len(inputs))(*inputs)
    sent = user32.SendInput(len(inputs), array, ctypes.sizeof(INPUT))
    if sent != len(inputs):
        raise ctypes.WinError(ctypes.get_last_error())


def send_chord(chord: Chord) -> None:
    """キーの組み合わせを押して離す。

    押下と解放を 1 回の SendInput にまとめ、間に他の入力が挟まらないようにする。
    """
    _send([_vk_input(vk, up) for vk, up in chord.key_events()])


def utf16_units(text: str) -> list[int]:
    """文字列を UTF-16 のコード単位に分ける（サロゲートペアは 2 単位になる）。"""
    data = text.encode("utf-16-le")
    return [int.from_bytes(data[i : i + 2], "little") for i in range(0, len(data), 2)]


def send_unicode(text: str) -> None:
    """文字列を KEYEVENTF_UNICODE で送る。

    1 文字ごとに押下と解放を対にし、サロゲートペアは連続して送る。
    """
    if text:
        _send(_pairs(utf16_units(text)))


def _pairs(units: list[int]) -> list[INPUT]:
    """コード単位の列を、押下・解放の対の列にする。サロゲートペアは両方の押下の後に両方を離す。"""
    inputs: list[INPUT] = []
    i = 0
    while i < len(units):
        u = units[i]
        group = units[i : i + 2] if 0xD800 <= u <= 0xDBFF else [u]
        inputs += [_unicode_input(c, False) for c in group]
        inputs += [_unicode_input(c, True) for c in group]
        i += len(group)
    return inputs


def modifiers_pressed() -> bool:
    """Ctrl / Alt / Shift / Win のどれかが物理的に押されているか。"""
    return any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in _MODIFIER_STATE_VK)


def release_modifiers() -> None:
    """修飾キーの解放を送る（テストや異常時の後始末用）。"""
    _send([_vk_input(vk, True) for vk in MODIFIER_VK.values()])
