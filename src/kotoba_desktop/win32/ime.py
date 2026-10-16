"""前面ウィンドウの IME の ON / OFF を取得・変更する（打鍵方式で使う）。

他プロセスのウィンドウでも、既定の IME ウィンドウに WM_IME_CONTROL を送れば操作できる。
"""

import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
imm32 = ctypes.WinDLL("imm32", use_last_error=True)

WM_IME_CONTROL = 0x0283
IMC_GETOPENSTATUS = 0x0005
IMC_SETOPENSTATUS = 0x0006
SMTO_ABORTIFHUNG = 0x0002

imm32.ImmGetDefaultIMEWnd.argtypes = (wintypes.HWND,)
imm32.ImmGetDefaultIMEWnd.restype = wintypes.HWND
user32.SendMessageTimeoutW.argtypes = (
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
    wintypes.UINT,
    wintypes.UINT,
    ctypes.POINTER(ctypes.c_size_t),
)
user32.SendMessageTimeoutW.restype = wintypes.LPARAM


def _send(hwnd: int, command: int, value: int) -> int | None:
    ime = imm32.ImmGetDefaultIMEWnd(hwnd)
    if not ime:
        return None
    result = ctypes.c_size_t()
    ok = user32.SendMessageTimeoutW(
        ime, WM_IME_CONTROL, command, value, SMTO_ABORTIFHUNG, 200, ctypes.byref(result)
    )
    return result.value if ok else None


def is_open(hwnd: int) -> bool | None:
    """IME が ON か。IME が無い・応答が無いときは None。"""
    status = _send(hwnd, IMC_GETOPENSTATUS, 0)
    return None if status is None else bool(status)


def set_open(hwnd: int, open_: bool) -> bool:
    """IME を ON / OFF にする。送れたら True。"""
    return _send(hwnd, IMC_SETOPENSTATUS, int(open_)) is not None
