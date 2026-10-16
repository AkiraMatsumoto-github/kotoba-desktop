"""前面ウィンドウのプロセス名・ウィンドウクラス・管理者権限の判定。"""

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import PureWindowsPath

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TOKEN_QUERY = 0x0008
TOKEN_ELEVATION = 20

user32.GetForegroundWindow.argtypes = ()
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.GetClassNameW.restype = ctypes.c_int
kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.GetCurrentProcess.argtypes = ()
kernel32.GetCurrentProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = (
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
)
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
advapi32.OpenProcessToken.argtypes = (
    wintypes.HANDLE,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.HANDLE),
)
advapi32.OpenProcessToken.restype = wintypes.BOOL
advapi32.GetTokenInformation.argtypes = (
    wintypes.HANDLE,
    ctypes.c_int,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
)
advapi32.GetTokenInformation.restype = wintypes.BOOL


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    pid: int
    process_name: str  # 例: "WindowsTerminal.exe"。取得できなければ空
    class_name: str
    elevated: bool  # 管理者として動いているか。調べられなければ True（入力しない側に倒す）


def _token_elevated(process: int) -> bool | None:
    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(process, TOKEN_QUERY, ctypes.byref(token)):
        return None
    try:
        value = wintypes.DWORD()
        size = wintypes.DWORD()
        ok = advapi32.GetTokenInformation(
            token, TOKEN_ELEVATION, ctypes.byref(value), ctypes.sizeof(value), ctypes.byref(size)
        )
        return bool(value.value) if ok else None
    finally:
        kernel32.CloseHandle(token)


def self_elevated() -> bool:
    """このプロセス自身が管理者として動いているか。"""
    return bool(_token_elevated(kernel32.GetCurrentProcess()))


def window_info(hwnd: int) -> WindowInfo:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, len(buf))
    class_name = buf.value

    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    process = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not process:
        return WindowInfo(hwnd, pid.value, "", class_name, elevated=True)
    try:
        path = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(path))
        name = ""
        if kernel32.QueryFullProcessImageNameW(process, 0, path, ctypes.byref(size)):
            name = PureWindowsPath(path.value).name
        elevated = _token_elevated(process)
    finally:
        kernel32.CloseHandle(process)
    return WindowInfo(
        hwnd, pid.value, name, class_name, elevated=True if elevated is None else elevated
    )


def foreground() -> WindowInfo | None:
    """前面ウィンドウの情報。前面ウィンドウが無ければ None。"""
    hwnd = user32.GetForegroundWindow()
    return window_info(hwnd) if hwnd else None


GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
MONITOR_DEFAULTTONEAREST = 2

user32.GetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int)
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.SetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t)
user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.MonitorFromWindow.argtypes = (wintypes.HWND, wintypes.DWORD)
user32.MonitorFromWindow.restype = wintypes.HMONITOR


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = (
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * 32),
    )


user32.GetMonitorInfoW.argtypes = (wintypes.HMONITOR, ctypes.POINTER(MONITORINFOEXW))
user32.GetMonitorInfoW.restype = wintypes.BOOL
user32.MonitorFromPoint.argtypes = (wintypes.POINT, wintypes.DWORD)
user32.MonitorFromPoint.restype = wintypes.HMONITOR
user32.GetCursorPos.argtypes = (ctypes.POINTER(wintypes.POINT),)
user32.GetCursorPos.restype = wintypes.BOOL
user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
user32.GetWindowRect.restype = wintypes.BOOL
user32.SetWindowPos.argtypes = (
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
)
user32.SetWindowPos.restype = wintypes.BOOL

HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
MONITOR_DEFAULTTONULL = 0


def make_no_activate(hwnd: int) -> None:
    """クリックしてもアクティブにならず、タスクバーにも出ない最前面のウィンドウにする。

    スクリーンキーボードと同じ作りで、クリックしてもキーボードフォーカスが元のアプリに残る。
    """
    style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongPtrW(
        hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST
    )


def raise_topmost(hwnd: int) -> None:
    """最前面の窓の中でも一番手前に出す。WS_EX_TOPMOST を付けるだけでは順番は変わらない。"""
    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)


# 以下の座標はすべて物理ピクセル。Qt の論理座標は DPI の違うモニターをまたぐと食い違うので、
# ウィジェットの移動と位置の保存はこちらで行う


def cursor_pos() -> tuple[int, int]:
    p = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def window_rect(hwnd: int) -> tuple[int, int, int, int]:
    """(左, 上, 幅, 高さ)。"""
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def move_window(hwnd: int, x: int, y: int) -> None:
    """左上を (x, y) に動かす。

    Qt の setPosition() だと途中で DPI が変わったときに大きさが物理ピクセルのまま残り、
    モニターをまたぐたびにウィンドウが縮む。Windows に直接動かさせると DPI に合わせて拡縮される。
    """
    user32.SetWindowPos(hwnd, None, x, y, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)


def on_any_monitor(x: int, y: int) -> bool:
    return bool(user32.MonitorFromPoint(wintypes.POINT(x, y), MONITOR_DEFAULTTONULL))


def foreground_monitor_origin() -> tuple[int, int] | None:
    """前面ウィンドウがあるモニターの左上（物理座標）。

    Qt 6 の QScreen.geometry() は左上を物理座標で持つので、DPI 対応のプロセス（Qt アプリ）なら
    これと一致する QScreen を探せばよい（QScreen.name() は表示名なので突き合わせに使えない）。
    """
    hwnd = user32.GetForegroundWindow()
    monitor = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    info = MONITORINFOEXW()
    info.cbSize = ctypes.sizeof(info)
    if not monitor or not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return None
    return info.rcMonitor.left, info.rcMonitor.top


user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.IsWindow.argtypes = (wintypes.HWND,)
user32.IsWindow.restype = wintypes.BOOL

# トレイを開いたときに前面になるタスクバーまわりのウィンドウ。入力先としては記録しない
_SHELL_CLASSES = frozenset(
    {
        "Shell_TrayWnd",
        "Shell_SecondaryTrayWnd",
        "NotifyIconOverflowWindow",
        "TopLevelWindowForOverflowXamlIsland",
        "Xaml_WindowedPopupClass",
    }
)


def is_input_target(info: WindowInfo, self_pid: int) -> bool:
    """再入力の入力先として覚えてよいウィンドウか（自分とタスクバーは除く）。"""
    return info.pid != self_pid and info.class_name not in _SHELL_CLASSES


def activate(hwnd: int) -> bool:
    """hwnd を前面に戻す。トレイのメニュー操作の直後なら、このプロセスから前面を切り替えられる。"""
    return bool(user32.IsWindow(hwnd) and user32.SetForegroundWindow(hwnd))
