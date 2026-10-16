"""ウィジェット（Widget.qml）の表示とボタン操作。

クリックしても入力先のフォーカスを奪わないことが必須条件。Qt の WindowDoesNotAcceptFocus に加えて
WS_EX_NOACTIVATE を直接付け、表示するときもアクティブにしない。
"""

import logging
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, QTimer, Signal, Slot
from PySide6.QtGui import QGuiApplication, QScreen, QWindow
from PySide6.QtQml import QQmlApplicationEngine

from kotoba_desktop.controller import Controller, State
from kotoba_desktop.state import State as AppState
from kotoba_desktop.win32.window import (
    cursor_pos,
    foreground_monitor_origin,
    make_no_activate,
    move_window,
    on_any_monitor,
    raise_topmost,
    window_rect,
)

log = logging.getLogger(__name__)

QML = Path(__file__).with_name("Widget.qml")
HIDE_DELAY_MS = 2000
BOTTOM_MARGIN = 48  # 作業領域の下端（タスクバーの上）からの距離
POS_KEY = "widget_pos_px"  # 左上の物理座標


class Widget(QObject):
    settingsRequested = Signal()
    helpRequested = Signal()

    def __init__(self, controller: Controller, app_state: AppState, always_show: bool) -> None:
        super().__init__()
        self._controller = controller
        self._app_state = app_state
        self._always_show = always_show

        self._engine = QQmlApplicationEngine()
        context = self._engine.rootContext()
        context.setContextProperty("controller", controller)
        context.setContextProperty("widget", self)
        self._engine.load(QML)
        roots = self._engine.rootObjects()
        if not roots:
            raise RuntimeError(f"{QML.name} を読み込めません")
        window = roots[0]
        assert isinstance(window, QWindow)
        self.window = window
        self._hwnd = int(window.winId())
        self._drag: tuple[int, int, int, int] | None = None  # カーソルとウィンドウの開始位置
        # 表示するときに前面ウィンドウを奪わない（Qt が SW_SHOWNOACTIVATE で表示する）
        self.window.setProperty("_q_showWithoutActivating", True)
        make_no_activate(self._hwnd)

        self._hide_timer = QTimer(self, singleShot=True, interval=HIDE_DELAY_MS)
        self._hide_timer.timeout.connect(self._hide_if_idle)
        controller.stateChanged.connect(self._on_state)
        controller.bubbleChanged.connect(self._on_bubble)
        if always_show:
            self.show()

    # --- 表示 ---

    def set_always_show(self, value: bool) -> None:
        self._always_show = value
        if value:
            self.show()
        else:
            self._hide_if_idle()

    def show(self) -> None:
        self._hide_timer.stop()
        if not self.window.isVisible():
            self._place()
            self.window.show()
            # show() で属性が戻ることがあるので付け直す
            make_no_activate(self._hwnd)
        # 後から出た最前面の窓（タスクバーなど）に隠れたままにならないよう、出すたびに手前へ
        raise_topmost(self._hwnd)

    def hide(self) -> None:
        self._hide_timer.stop()
        self.window.hide()

    def _hide_if_idle(self) -> None:
        idle = self._controller.current in (State.IDLE, State.LOADING, State.FAILED)
        if idle and not self._always_show and not self._controller.bubble:
            self.window.hide()
        elif idle and not self._always_show:
            self._hide_timer.start()  # 吹き出しが消えるのを待つ

    def _on_state(self) -> None:
        if self._controller.current in (State.RECORDING, State.RECOGNIZING, State.INJECTING):
            self.show()
        elif self.window.isVisible():
            self._hide_timer.start()

    def _on_bubble(self) -> None:
        # エラーはウィジェットが出ていなくても見せる
        if self._controller.error:
            self.show()
            self._hide_timer.start()

    def _screen_for_foreground(self) -> QScreen:
        origin = foreground_monitor_origin()
        if origin:
            for screen in QGuiApplication.screens():
                g = screen.geometry()
                if (g.left(), g.top()) == origin:
                    return screen
        return QGuiApplication.primaryScreen()

    def _place(self) -> None:
        """保存した位置に置く。その位置のモニターが無くなっていれば前面のモニターの下部中央。"""
        saved = self._app_state.get(POS_KEY)
        if isinstance(saved, list) and len(saved) == 2:
            x, y = int(saved[0]), int(saved[1])
            _, _, w, h = window_rect(self._hwnd)
            if on_any_monitor(x + w // 2, y + h // 2):
                move_window(self._hwnd, x, y)
                return
        area = self._screen_for_foreground().availableGeometry()
        self.window.setPosition(
            QPoint(
                area.center().x() - self.window.width() // 2,
                area.bottom() - self.window.height() - BOTTOM_MARGIN,
            )
        )

    # --- QML から呼ばれる ---

    @Slot()
    def micClicked(self) -> None:
        self._controller.toggle()

    @Slot()
    def close(self) -> None:
        self._controller.cancel()
        self.hide()

    @Slot()
    def openSettings(self) -> None:
        self.settingsRequested.emit()

    @Slot()
    def showHelp(self) -> None:
        self.helpRequested.emit()

    # ドラッグは物理座標で Windows に直接動かさせる（move_window の説明を参照）

    @Slot()
    def dragStarted(self) -> None:
        cx, cy = cursor_pos()
        x, y, _, _ = window_rect(self._hwnd)
        self._drag = (cx, cy, x, y)

    @Slot()
    def dragMoved(self) -> None:
        if self._drag is None:
            return
        cx, cy, x, y = self._drag
        px, py = cursor_pos()
        move_window(self._hwnd, x + px - cx, y + py - cy)

    @Slot()
    def dragFinished(self) -> None:
        if self._drag is None:
            return
        self._drag = None
        x, y, _, _ = window_rect(self._hwnd)
        self._app_state.set(POS_KEY, [x, y])
