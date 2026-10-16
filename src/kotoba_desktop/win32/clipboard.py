"""クリップボードの退避・書き込み・復元。

書き込むときは Win+V の履歴とクラウド同期から外す形式も一緒に置く。
"""

import ctypes
import time
from collections.abc import Generator
from contextlib import contextmanager
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

# HGLOBAL 以外のハンドルを持つ形式。中身をバイト列として退避できないので扱わない。
# CF_BITMAP などは CF_DIB から OS が合成するため、画像は CF_DIB / CF_DIBV5 の退避で戻る。
_NON_HGLOBAL_FORMATS = frozenset(
    {
        2,  # CF_BITMAP
        3,  # CF_METAFILEPICT
        9,  # CF_PALETTE
        14,  # CF_ENHMETAFILE
        0x0080,  # CF_OWNERDISPLAY
        0x0082,  # CF_DSPBITMAP
        0x0083,  # CF_DSPMETAFILEPICT
        0x008E,  # CF_DSPENHMETAFILE
    }
)

user32.OpenClipboard.argtypes = (wintypes.HWND,)
user32.OpenClipboard.restype = wintypes.BOOL
user32.CloseClipboard.argtypes = ()
user32.CloseClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.argtypes = ()
user32.EmptyClipboard.restype = wintypes.BOOL
user32.EnumClipboardFormats.argtypes = (wintypes.UINT,)
user32.EnumClipboardFormats.restype = wintypes.UINT
user32.GetClipboardData.argtypes = (wintypes.UINT,)
user32.GetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = (wintypes.UINT, wintypes.HANDLE)
user32.SetClipboardData.restype = wintypes.HANDLE
user32.RegisterClipboardFormatW.argtypes = (wintypes.LPCWSTR,)
user32.RegisterClipboardFormatW.restype = wintypes.UINT
user32.GetClipboardSequenceNumber.argtypes = ()
user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
kernel32.GlobalAlloc.argtypes = (wintypes.UINT, ctypes.c_size_t)
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalFree.argtypes = (wintypes.HGLOBAL,)
kernel32.GlobalFree.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = (wintypes.HGLOBAL,)
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = (wintypes.HGLOBAL,)
kernel32.GlobalUnlock.restype = wintypes.BOOL
kernel32.GlobalSize.argtypes = (wintypes.HGLOBAL,)
kernel32.GlobalSize.restype = ctypes.c_size_t

# 履歴（Win+V）・クラウド同期・クリップボード監視ツールから外すための登録形式
_EXCLUDE_FORMATS = {
    "ExcludeClipboardContentFromMonitorProcessing": b"\x00",
    "CanIncludeInClipboardHistory": (0).to_bytes(4, "little"),
    "CanUploadToCloudClipboard": (0).to_bytes(4, "little"),
}

Snapshot = list[tuple[int, bytes]]


def _is_hglobal(fmt: int) -> bool:
    # CF_PRIVATEFIRST〜LAST（0x200〜0x2FF）と CF_GDIOBJFIRST〜LAST（0x300〜0x3FF）の
    # ハンドルは HGLOBAL とは限らないので、中身を読まない
    return fmt not in _NON_HGLOBAL_FORMATS and not 0x0200 <= fmt <= 0x03FF


class ClipboardError(OSError):
    pass


@contextmanager
def _opened(retries: int = 20, interval: float = 0.01) -> Generator[None]:
    """クリップボードを開く。他のアプリが開いている間は少し待って再試行する。"""
    for _ in range(retries):
        if user32.OpenClipboard(None):
            break
        time.sleep(interval)
    else:
        raise ClipboardError("クリップボードを開けません（他のアプリが使用中）")
    try:
        yield
    finally:
        user32.CloseClipboard()


def _read_hglobal(handle: int) -> bytes | None:
    size = kernel32.GlobalSize(handle)
    ptr = kernel32.GlobalLock(handle)
    if not ptr:
        return None
    try:
        return ctypes.string_at(ptr, size)
    finally:
        kernel32.GlobalUnlock(handle)


def _set_bytes(fmt: int, data: bytes) -> None:
    """data を GlobalAlloc した領域に写して SetClipboardData する。

    成功すると領域の所有は OS に移るので、解放するのは失敗したときだけ。
    """
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, max(len(data), 1))
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    ptr = kernel32.GlobalLock(handle)
    if not ptr:
        kernel32.GlobalFree(handle)
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        ctypes.memmove(ptr, data, len(data))
    finally:
        kernel32.GlobalUnlock(handle)
    if not user32.SetClipboardData(fmt, handle):
        kernel32.GlobalFree(handle)
        raise ctypes.WinError(ctypes.get_last_error())


def _set_excluded() -> None:
    for name, data in _EXCLUDE_FORMATS.items():
        _set_bytes(user32.RegisterClipboardFormatW(name), data)


def sequence_number() -> int:
    """クリップボードの更新番号。内容が変わるたびに増える。"""
    return user32.GetClipboardSequenceNumber()


def snapshot() -> Snapshot:
    """今の内容を退避する。HGLOBAL で持てる形式だけを (形式, バイト列) の列で返す。"""
    saved: Snapshot = []
    with _opened():
        fmt = user32.EnumClipboardFormats(0)
        while fmt:
            if _is_hglobal(fmt):
                handle = user32.GetClipboardData(fmt)
                data = _read_hglobal(handle) if handle else None
                if data is not None:
                    saved.append((fmt, data))
            fmt = user32.EnumClipboardFormats(fmt)
    return saved


def restore(saved: Snapshot, retries: int = 20) -> None:
    """snapshot() の内容に戻す。履歴に重複して載らないよう、除外形式も一緒に置く。"""
    with _opened(retries):
        user32.EmptyClipboard()
        if not saved:
            return
        for fmt, data in saved:
            _set_bytes(fmt, data)
        _set_excluded()


def set_text(text: str) -> int:
    """text を CF_UNICODETEXT で置き、履歴と同期から外す。置いた後の更新番号を返す。"""
    with _opened():
        if not user32.EmptyClipboard():
            raise ctypes.WinError(ctypes.get_last_error())
        _set_bytes(CF_UNICODETEXT, (text + "\0").encode("utf-16-le"))
        _set_excluded()
    return sequence_number()


def get_text() -> str | None:
    """CF_UNICODETEXT の内容を返す。無ければ None。"""
    with _opened():
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        data = _read_hglobal(handle) if handle else None
    if data is None:
        return None
    return data.decode("utf-16-le").split("\0", 1)[0]
