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
from kotoba_desktop.win32.window import foreground_monitor_origin, make_no_activate

log = logging.getLogger(__name__)

QML = Path(__file__).with_name("Widget.qml")
HIDE_DELAY_MS = 2000
BOTTOM_MARGIN = 48  # 作業領域の下端（タスクバーの上）からの距離


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
        # 表示するときに前面ウィンドウを奪わない（Qt が SW_SHOWNOACTIVATE で表示する）
        self.window.setProperty("_q_showWithoutActivating", True)
        make_no_activate(int(self.window.winId()))

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
        if self.window.isVisible():
            return
        self.window.setPosition(self._initial_position())
        self.window.show()
        # show() で属性が戻ることがあるので付け直す
        make_no_activate(int(self.window.winId()))

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

    def _initial_position(self) -> QPoint:
        saved = self._app_state.get("widget_pos")
        if isinstance(saved, list) and len(saved) == 2:
            pos = QPoint(int(saved[0]), int(saved[1]))
            center = pos + QPoint(self.window.width() // 2, self.window.height() // 2)
            if QGuiApplication.screenAt(center) is not None:
                return pos
        area = self._screen_for_foreground().availableGeometry()
        return QPoint(
            area.center().x() - self.window.width() // 2,
            area.bottom() - self.window.height() - BOTTOM_MARGIN,
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

    @Slot(int, int)
    def savePosition(self, x: int, y: int) -> None:
        self._app_state.set("widget_pos", [x, y])
