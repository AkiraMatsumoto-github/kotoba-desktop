"""タスクトレイのアイコンとメニュー。"""

from collections.abc import Callable, Sequence

from PySide6.QtCore import QObject, QRectF, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from kotoba_desktop.controller import Controller, State

MENU_TEXT_CHARS = 30

_STATE_LABEL = {
    State.LOADING: "モデルを読み込み中",
    State.IDLE: "待機中",
    State.RECORDING: "録音中",
    State.RECOGNIZING: "認識中",
    State.INJECTING: "入力中",
    State.FAILED: "使用不可",
}

_STATE_COLOR = {
    State.IDLE: "#0078d4",
    State.RECORDING: "#d13438",
    State.RECOGNIZING: "#0078d4",
    State.INJECTING: "#0078d4",
    State.LOADING: "#767676",
    State.FAILED: "#767676",
}


def make_icon(color: str) -> QIcon:
    """色付きの円にマイクの記号を描いたアイコン。"""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    painter.drawEllipse(2, 2, 60, 60)
    painter.setPen(QColor("white"))
    painter.setFont(QFont("Segoe Fluent Icons", 26))
    painter.drawText(QRectF(0, 0, 64, 64), Qt.AlignmentFlag.AlignCenter, "")
    painter.end()
    return QIcon(pixmap)


class Tray(QObject):
    settingsDialogRequested = Signal()
    quitRequested = Signal()
    showWidgetRequested = Signal()
    alwaysShowToggled = Signal(bool)
    deviceSelected = Signal(str)  # 空 = 既定のマイク

    def __init__(
        self,
        controller: Controller,
        list_devices: Callable[[], Sequence[str]],
        current_device: Callable[[], str],
        always_show: bool,
        last_target: Callable[[], int | None] = lambda: None,
    ) -> None:
        super().__init__()
        self._controller = controller
        self._list_devices = list_devices
        self._current_device = current_device
        self._last_target = last_target
        self._icons = {state: make_icon(color) for state, color in _STATE_COLOR.items()}

        self._menu = QMenu()
        self._history_menu = self._menu.addMenu("履歴")
        self._device_menu = self._menu.addMenu("マイク")
        self._device_menu.aboutToShow.connect(self._fill_devices)
        self._always_show = self._menu.addAction("ウィジェットを常に表示")
        self._always_show.setCheckable(True)
        self._always_show.setChecked(always_show)
        self._always_show.toggled.connect(self.alwaysShowToggled)
        self._menu.addSeparator()
        self._menu.addAction("設定…").triggered.connect(self.settingsDialogRequested)
        self._menu.addSeparator()
        self._menu.addAction("終了").triggered.connect(self.quitRequested)

        self._tray = QSystemTrayIcon()
        self._tray.setContextMenu(self._menu)
        self._tray.activated.connect(self._on_activated)
        controller.stateChanged.connect(self._update_state)
        controller.historyChanged.connect(self._fill_history)
        controller.notify.connect(self.show_message)
        self._update_state()
        self._fill_history()
        self._tray.show()

    def show_message(self, title: str, message: str) -> None:
        self._tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 5000)

    def set_always_show(self, value: bool) -> None:
        self._always_show.setChecked(value)

    def hide(self) -> None:
        self._tray.hide()

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        # 左クリックでウィジェットを出す。トレイのクリックで前面ウィンドウが変わるので録音は始めない
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.showWidgetRequested.emit()

    def _update_state(self) -> None:
        state = self._controller.current
        self._tray.setIcon(self._icons[state])
        self._tray.setToolTip(f"kotoba-desktop（{_STATE_LABEL[state]}）")

    def _fill_history(self) -> None:
        self._history_menu.clear()
        history = list(self._controller.history)
        self._history_menu.setEnabled(bool(history))
        for text in history:
            label = text if len(text) <= MENU_TEXT_CHARS else text[:MENU_TEXT_CHARS] + "…"
            action = self._history_menu.addAction(label.replace("&", "&&"))
            action.setToolTip(text)
            action.triggered.connect(
                lambda _=False, t=text: self._controller.reinject(t, self._last_target())
            )

    def _fill_devices(self) -> None:
        self._device_menu.clear()
        group = QActionGroup(self._device_menu)
        current = self._current_device()
        try:
            devices = list(self._list_devices())
        except Exception as e:
            self._device_menu.addAction(f"一覧を取得できません: {e}").setEnabled(False)
            return
        for name in ["", *devices]:
            action = QAction(name or "既定のマイク", self._device_menu, checkable=True)
            action.setChecked(name == current)
            action.triggered.connect(lambda _=False, n=name: self.deviceSelected.emit(n))
            group.addAction(action)
            self._device_menu.addAction(action)
