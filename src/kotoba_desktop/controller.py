"""待機 → 録音中 → 認識中 → 入力中 の状態遷移を管理する。

状態の変更はすべて UI スレッド（Qt のメインループ）で行う。ホットキー・録音・認識・入力の
各スレッドは post_* メソッドで知らせるだけで、Qt のキュー接続を通って UI スレッドの処理に渡る。
"""

import enum
import logging
from collections import deque
from collections.abc import Callable
from typing import Protocol

import numpy as np
from PySide6.QtCore import Property, QObject, Qt, QTimer, Signal, Slot

from kotoba_desktop.inject.injector import Result, Status
from kotoba_desktop.recognizer import Recognition

log = logging.getLogger(__name__)

HISTORY_SIZE = 10
DONE_BUBBLE_MS = 1500
ERROR_BUBBLE_MS = 4000
BUBBLE_CHARS = 20
REINJECT_DELAY_MS = 300  # トレイのメニューが閉じて元のウィンドウが前面に戻るのを待つ


class State(enum.StrEnum):
    LOADING = "loading"  # モデル読み込み中
    IDLE = "idle"
    RECORDING = "recording"
    RECOGNIZING = "recognizing"
    INJECTING = "injecting"
    FAILED = "failed"  # モデルを読み込めず使えない


class RecorderLike(Protocol):
    level: float

    def start(self) -> None: ...
    def stop(self) -> np.ndarray: ...
    def cancel(self) -> None: ...


class SubmitAudio(Protocol):
    def submit(self, audio: np.ndarray) -> None: ...


class SubmitText(Protocol):
    def submit(self, text: str, *, processed: bool = False, target: int | None = None) -> None: ...


class Controller(QObject):
    stateChanged = Signal()
    bubbleChanged = Signal()
    levelChanged = Signal()
    hotkeyTextChanged = Signal()
    historyChanged = Signal()
    notify = Signal(str, str)  # (タイトル, 本文)。トレイの通知に出す

    # 他スレッドから UI スレッドへ渡すための内部シグナル
    _toggle_requested = Signal()
    _mic_ready = Signal()
    _loaded = Signal(str)
    _recognized = Signal(object)
    _injected = Signal(object)

    def __init__(
        self,
        recorder: RecorderLike,
        recognizer: SubmitAudio,
        injector: SubmitText,
        hotkey_text: str = "",
    ) -> None:
        super().__init__()
        self.recorder = recorder
        self.recognizer = recognizer
        self.injector = injector
        self._state = State.LOADING
        self._bubble = "モデルを読み込み中…"
        self._error = False
        self._level = 0.0
        self._hotkey_text = hotkey_text
        self.history: deque[str] = deque(maxlen=HISTORY_SIZE)
        # 再入力の前に入力先を前面に戻す関数（テストでは差し替える）
        self.activate_window: Callable[[int], object] = lambda hwnd: None

        self._bubble_timer = QTimer(self, singleShot=True)
        self._bubble_timer.timeout.connect(self._clear_bubble)
        self._level_timer = QTimer(self, interval=33)
        self._level_timer.timeout.connect(self._poll_level)

        queued = Qt.ConnectionType.QueuedConnection
        self._toggle_requested.connect(self.toggle, queued)
        self._mic_ready.connect(self._on_mic_ready, queued)
        self._loaded.connect(self._on_loaded, queued)
        self._recognized.connect(self._on_recognized, queued)
        self._injected.connect(self._on_injected, queued)

    # --- 他スレッドから呼ぶ ---

    def post_toggle(self) -> None:
        self._toggle_requested.emit()

    def post_mic_ready(self) -> None:
        self._mic_ready.emit()

    def post_loaded(self, error: str) -> None:
        self._loaded.emit(error)

    def post_recognized(self, result: Recognition) -> None:
        self._recognized.emit(result)

    def post_inject_result(self, result: Result) -> None:
        self._injected.emit(result)

    # --- QML に見せるプロパティ ---

    def _get_state(self) -> str:
        return self._state.value

    def _get_bubble(self) -> str:
        return self._bubble

    def _get_error(self) -> bool:
        return self._error

    def _get_level(self) -> float:
        return self._level

    def _get_hotkey_text(self) -> str:
        return self._hotkey_text

    state = Property(str, _get_state, notify=stateChanged)
    bubble = Property(str, _get_bubble, notify=bubbleChanged)
    error = Property(bool, _get_error, notify=bubbleChanged)
    level = Property(float, _get_level, notify=levelChanged)
    hotkeyText = Property(str, _get_hotkey_text, notify=hotkeyTextChanged)

    @property
    def current(self) -> State:
        return self._state

    def show_message(self, text: str, *, error: bool = False, timeout_ms: int = 3000) -> None:
        """吹き出しに一時的に表示する（ヘルプや設定の再読み込み結果など）。"""
        self._set_bubble(text, error=error, timeout_ms=timeout_ms)

    def set_hotkey_text(self, text: str) -> None:
        self._hotkey_text = text
        self.hotkeyTextChanged.emit()

    # --- 状態遷移 ---

    def _set_state(self, state: State) -> None:
        if state != self._state:
            log.debug("状態 %s → %s", self._state, state)
            self._state = state
            self.stateChanged.emit()
        if state == State.RECORDING:
            self._level_timer.start()
        else:
            self._level_timer.stop()
            self._set_level(0.0)

    def _set_bubble(self, text: str, *, error: bool = False, timeout_ms: int = 0) -> None:
        self._bubble = text
        self._error = error
        self.bubbleChanged.emit()
        if timeout_ms:
            self._bubble_timer.start(timeout_ms)
        else:
            self._bubble_timer.stop()

    def _clear_bubble(self) -> None:
        self._set_bubble("")

    def _set_level(self, level: float) -> None:
        if level != self._level:
            self._level = level
            self.levelChanged.emit()

    def _poll_level(self) -> None:
        self._set_level(self.recorder.level)

    def _fail(self, message: str) -> None:
        self._set_bubble(message, error=True, timeout_ms=ERROR_BUBBLE_MS)
        self.notify.emit("kotoba-desktop", message)

    @Slot()
    def toggle(self) -> None:
        """ショートカットキーかマイクボタンが押された。"""
        match self._state:
            case State.IDLE:
                try:
                    self.recorder.start()
                except Exception as e:
                    log.exception("録音を開始できません")
                    self._fail(str(e))
                    return
                self._set_state(State.RECORDING)
                # マイクから最初の音が届くまでは「準備中」。届いたら _on_mic_ready で切り替える
                # （録音スレッドからの通知はキュー経由なので、必ずこの後に処理される）
                self._set_bubble("準備中…")
            case State.RECORDING:
                try:
                    audio = self.recorder.stop()
                except Exception as e:
                    log.exception("録音を終了できません")
                    self._set_state(State.IDLE)
                    self._fail(f"録音を終了できません: {e}")
                    return
                self._set_state(State.RECOGNIZING)
                self._set_bubble("変換中…")
                self.recognizer.submit(audio)
            case State.LOADING:
                self._set_bubble("モデルを読み込み中…")
            case State.FAILED:
                self._fail("モデルを読み込めなかったため使えません。ログを確認してください")
            case _:
                pass  # 認識中・入力中の押下は無視する（二重に動かさない）

    @Slot()
    def cancel(self) -> None:
        """録音中なら破棄する（ウィジェットの閉じるボタン）。"""
        if self._state == State.RECORDING:
            self.recorder.cancel()
            self._set_state(State.IDLE)
            self._clear_bubble()

    def reinject(self, text: str, target: int | None = None) -> None:
        """履歴の文を入力し直す。

        target はトレイを開く前に前面にあったウィンドウ。そこを前面に戻してから入力し、戻らなければ
        クリップボードに置くだけにする（トレイを開くと前面がタスクバーに移るため）。
        """
        if self._state != State.IDLE:
            self._set_bubble("処理中のため再入力できません", error=True, timeout_ms=ERROR_BUBBLE_MS)
            return
        self._set_state(State.INJECTING)

        def submit() -> None:
            if target is not None:
                self.activate_window(target)
            self.injector.submit(text, processed=True, target=target)

        QTimer.singleShot(REINJECT_DELAY_MS, submit)

    @Slot()
    def _on_mic_ready(self) -> None:
        if self._state == State.RECORDING:
            self._set_bubble("聞き取り中…")

    @Slot(str)
    def _on_loaded(self, error: str) -> None:
        if error:
            self._set_state(State.FAILED)
            self._fail(error)
            return
        self._set_state(State.IDLE)
        self._clear_bubble()

    @Slot(object)
    def _on_recognized(self, result: Recognition) -> None:
        if result.error:
            self._set_state(State.IDLE)
            self._fail(result.error)
        elif not result.text:
            self._set_state(State.IDLE)
            self._set_bubble("聞き取れませんでした", timeout_ms=DONE_BUBBLE_MS)
        else:
            self._set_state(State.INJECTING)
            self.injector.submit(result.text)

    @Slot(object)
    def _on_injected(self, result: Result) -> None:
        self._set_state(State.IDLE)
        if result.text:
            if result.text in self.history:
                self.history.remove(result.text)
            self.history.appendleft(result.text)
            self.historyChanged.emit()
        match result.status:
            case Status.INJECTED:
                head = result.text[:BUBBLE_CHARS] + ("…" if len(result.text) > BUBBLE_CHARS else "")
                self._set_bubble(head, timeout_ms=DONE_BUBBLE_MS)
            case Status.EMPTY:
                self._set_bubble("聞き取れませんでした", timeout_ms=DONE_BUBBLE_MS)
            case Status.CLIPBOARD_ONLY:
                self._set_bubble("Ctrl+V で貼ってください", timeout_ms=ERROR_BUBBLE_MS)
                self.notify.emit("kotoba-desktop", result.status.value)
            case _:
                message = result.status.value + (f"（{result.detail}）" if result.detail else "")
                self._fail(message + "。トレイの履歴から入力し直せます")
