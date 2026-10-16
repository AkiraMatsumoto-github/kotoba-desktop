"""名前付きミューテックスで二重起動を防ぐ。"""

import ctypes
from ctypes import wintypes

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
kernel32.CreateMutexW.restype = wintypes.HANDLE

ERROR_ALREADY_EXISTS = 183
MUTEX_NAME = r"Local\kotoba-desktop-single-instance"

_handle: int | None = None


def acquire() -> bool:
    """このプロセスが最初の 1 つなら True。ハンドルはプロセス終了まで保持する。"""
    global _handle
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        return False
    _handle = handle
    return True
