"""RegisterHotKey でショートカットキーを登録し、押下を待ち受ける。

登録とメッセージループは同じスレッドで行う必要があるので、専用のスレッドを 1 本立てる。
"""

import ctypes
import logging
import threading
from collections.abc import Callable
from ctypes import wintypes

from kotoba_desktop.keys import Chord
from kotoba_desktop.win32.input import send_mask_key

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
MOD_NOREPEAT = 0x4000
PM_NOREMOVE = 0x0000
HOTKEY_ID = 1

log = logging.getLogger(__name__)

user32.RegisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT)
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int)
user32.UnregisterHotKey.restype = wintypes.BOOL
user32.GetMessageW.argtypes = (
    ctypes.POINTER(wintypes.MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
)
user32.GetMessageW.restype = wintypes.BOOL
user32.PeekMessageW.argtypes = (
    ctypes.POINTER(wintypes.MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
    wintypes.UINT,
)
user32.PeekMessageW.restype = wintypes.BOOL
user32.PostThreadMessageW.argtypes = (
    wintypes.DWORD,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
)
user32.PostThreadMessageW.restype = wintypes.BOOL
kernel32.GetCurrentThreadId.argtypes = ()
kernel32.GetCurrentThreadId.restype = wintypes.DWORD


class HotkeyError(OSError):
    pass


class HotkeyListener:
    """chord が押されるたびに on_press を呼ぶ（ホットキースレッドから呼ばれる）。"""

    def __init__(self, chord: Chord, on_press: Callable[[], None]) -> None:
        self.chord = chord
        self._on_press = on_press
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._ready = threading.Event()
        self._error: int | None = None
        # Win や Alt を含むと、離したときにスタートメニューやメニューバーが開くのを防ぐ必要がある
        self._needs_mask = bool({"win", "alt"} & set(chord.modifiers))

    def start(self) -> None:
        """登録してから戻る。他のアプリが同じキーを使っていれば HotkeyError。"""
        self._thread = threading.Thread(target=self._run, name="hotkey", daemon=True)
        self._thread.start()
        self._ready.wait()
        if self._error is not None:
            self._thread.join()
            raise HotkeyError(
                f"ショートカットキー {self.chord.display} を登録できません"
                f"（他のアプリが使用中の可能性があります。エラー {self._error}）"
            )

    def stop(self) -> None:
        if self._thread and self._thread.is_alive():
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            self._thread.join(timeout=2)

    def _run(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        msg = wintypes.MSG()
        # stop() の WM_QUIT を確実に受け取れるよう、先にメッセージキューを作らせる
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_NOREMOVE)
        flags = self.chord.hotkey_flags | MOD_NOREPEAT
        if not user32.RegisterHotKey(None, HOTKEY_ID, flags, self.chord.vk):
            self._error = ctypes.get_last_error()
            self._ready.set()
            return
        self._ready.set()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                    try:
                        if self._needs_mask:
                            send_mask_key()
                        self._on_press()
                    except Exception:
                        log.exception("ホットキーの処理で例外")
        finally:
            user32.UnregisterHotKey(None, HOTKEY_ID)
