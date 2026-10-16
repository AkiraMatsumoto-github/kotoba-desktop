"""入力専用のスレッド。先入れ先出しのキューから 1 件ずつ入力する。

入力の経路をこの 1 本に限ることで、複数の結果が続けて届いても順序が入れ替わらない。
"""

import enum
import os
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from kotoba_desktop import textproc
from kotoba_desktop.config import Config
from kotoba_desktop.inject.paste import TargetChanged
from kotoba_desktop.inject.profiles import resolve
from kotoba_desktop.win32.window import WindowInfo

MODIFIER_TIMEOUT_S = 2.0


class Status(enum.Enum):
    INJECTED = "入力しました"
    EMPTY = "入力する文字がありません"
    MODIFIER_TIMEOUT = "修飾キーが押されたままなので入力しませんでした"
    CLIPBOARD_ONLY = "入力できない画面なので、クリップボードに置きました（Ctrl+V で貼ってください）"
    ERROR = "入力に失敗しました"


@dataclass(frozen=True)
class Result:
    text: str  # 後処理後の文字列（EMPTY のときは空）
    status: Status
    detail: str = ""


@dataclass
class Backend:
    """Win32 の呼び出し。テストでは差し替える。"""

    foreground: Callable[[], WindowInfo | None]
    modifiers_pressed: Callable[[], bool]
    paste: Callable[..., str]  # (text, key, restore_delay_ms, still_target) -> 補足
    type_text: Callable[[int, str], None]
    set_clipboard: Callable[[str], object]
    self_elevated: bool = False
    self_pid: int = field(default_factory=os.getpid)


def default_backend() -> Backend:
    from kotoba_desktop.inject.paste import paste
    from kotoba_desktop.inject.typing import type_text
    from kotoba_desktop.win32 import clipboard, window
    from kotoba_desktop.win32.input import modifiers_pressed

    return Backend(
        foreground=window.foreground,
        modifiers_pressed=modifiers_pressed,
        paste=paste,
        type_text=type_text,
        set_clipboard=clipboard.set_text,
        self_elevated=window.self_elevated(),
    )


@dataclass(frozen=True)
class _Job:
    text: str
    processed: bool  # 後処理済み（履歴からの再入力）
    target: int | None  # 入力先のウィンドウ。指定したときは前面がこれでなければ入力しない


class Injector:
    def __init__(
        self,
        get_config: Callable[[], Config],
        on_result: Callable[[Result], None],
        backend: Backend | None = None,
    ) -> None:
        self._get_config = get_config
        self._on_result = on_result
        self._backend = backend or default_backend()
        self._queue: queue.Queue[_Job | None] = queue.Queue()
        self._thread = threading.Thread(target=self._run, name="injector", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._queue.put(None)
        self._thread.join(timeout=5)

    def submit(self, text: str, *, processed: bool = False, target: int | None = None) -> None:
        """入力待ちに加える。processed=True（履歴からの再入力）なら後処理をかけない。"""
        self._queue.put(_Job(text, processed, target))

    def _run(self) -> None:
        while (job := self._queue.get()) is not None:
            try:
                result = self.inject(job.text, processed=job.processed, target=job.target)
            except Exception as e:  # 入力スレッドは止めない
                # 履歴から入れ直したときに通常と同じ文字列になるよう、後処理済みの文字列を返す
                result = Result(self._postprocess(job.text, job.processed), Status.ERROR, str(e))
            self._on_result(result)

    def _postprocess(self, raw: str, processed: bool, punctuation: str | None = None) -> str:
        if processed:
            return raw
        cfg = self._get_config().text
        return textproc.process(
            raw,
            drop_phrases=cfg.drop_phrases,
            replace=cfg.replace,
            punctuation=punctuation or cfg.punctuation,
        )

    def _wait_modifiers_released(self) -> bool:
        deadline = time.monotonic() + MODIFIER_TIMEOUT_S
        while self._backend.modifiers_pressed():
            if time.monotonic() > deadline:
                return False
            time.sleep(0.01)
        return True

    def inject(self, raw: str, *, processed: bool = False, target: int | None = None) -> Result:
        """1 件を入力する。入力スレッドから呼ぶ（テストでは直接呼ぶ）。"""
        b = self._backend
        cfg = self._get_config()

        # 終了キーの Ctrl などが離れる前に貼り付けキーを送ると別のショートカットに化ける
        if not self._wait_modifiers_released():
            text = self._postprocess(raw, processed)
            return Result(text, Status.MODIFIER_TIMEOUT if text else Status.EMPTY)

        win = b.foreground()
        profile = resolve(
            cfg.inject,
            cfg.text.punctuation,
            win.process_name if win else "",
            win.class_name if win else "",
        )
        text = self._postprocess(raw, processed, profile.punctuation)
        if not text:
            return Result("", Status.EMPTY)

        # 管理者として動くウィンドウには SendInput が届かない（UIPI）。
        # 自分のウィンドウ（トレイのメニューなど）や、指定と違うウィンドウにも入力しない
        if (
            win is None
            or win.pid == b.self_pid
            or (win.elevated and not b.self_elevated)
            or (target is not None and win.hwnd != target)
        ):
            b.set_clipboard(text)
            return Result(text, Status.CLIPBOARD_ONLY, win.process_name if win else "")

        if profile.method == "type":
            b.type_text(win.hwnd, text)
            return Result(text, Status.INJECTED, f"{win.process_name}（打鍵）")

        def still_target() -> bool:
            now = b.foreground()
            return now is not None and now.hwnd == win.hwnd

        try:
            note = b.paste(text, profile.paste_key, profile.restore_delay_ms, still_target)
        except TargetChanged:
            b.set_clipboard(text)
            return Result(text, Status.CLIPBOARD_ONLY, "入力先のウィンドウが切り替わったため")
        detail = f"{win.process_name}（{profile.paste_key}）"
        return Result(text, Status.INJECTED, f"{detail}。{note}" if note else detail)
