"""設定画面。よく変える項目（ショートカットキー、マイク、句読点、置換辞書など）だけを扱う。"""

from collections.abc import Callable, Sequence

from pydantic import ValidationError
from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from kotoba_desktop.config import Config
from kotoba_desktop.keys import Chord, key_name, parse_chord

_QT_MODIFIERS = (
    (Qt.KeyboardModifier.MetaModifier, "win"),  # Windows では Win キーが Meta になる
    (Qt.KeyboardModifier.ControlModifier, "ctrl"),
    (Qt.KeyboardModifier.AltModifier, "alt"),
    (Qt.KeyboardModifier.ShiftModifier, "shift"),
)

# 修飾キーそのもの → 名前。押したイベントの modifiers() には自分自身が含まれないことがある
_MODIFIER_KEYS = {
    Qt.Key.Key_Control: "ctrl",
    Qt.Key.Key_Shift: "shift",
    Qt.Key.Key_Alt: "alt",
    Qt.Key.Key_AltGr: "alt",
    Qt.Key.Key_Meta: "win",
    Qt.Key.Key_Super_L: "win",
    Qt.Key.Key_Super_R: "win",
}

# nativeVirtualKey が取れないとき（テストなど）に使う Qt のキー → キー名
_QT_KEY_NAMES = {
    **{Qt.Key(Qt.Key.Key_A.value + i): chr(ord("a") + i) for i in range(26)},
    **{Qt.Key(Qt.Key.Key_0.value + i): str(i) for i in range(10)},
    **{Qt.Key(Qt.Key.Key_F1.value + i): f"f{i + 1}" for i in range(24)},
    Qt.Key.Key_Space: "space",
    Qt.Key.Key_Tab: "tab",
    Qt.Key.Key_Return: "enter",
    Qt.Key.Key_Enter: "enter",
    Qt.Key.Key_Backspace: "backspace",
    Qt.Key.Key_Escape: "esc",
    Qt.Key.Key_Insert: "insert",
    Qt.Key.Key_Delete: "delete",
    Qt.Key.Key_Home: "home",
    Qt.Key.Key_End: "end",
    Qt.Key.Key_PageUp: "pageup",
    Qt.Key.Key_PageDown: "pagedown",
    Qt.Key.Key_Left: "left",
    Qt.Key.Key_Right: "right",
    Qt.Key.Key_Up: "up",
    Qt.Key.Key_Down: "down",
    Qt.Key.Key_Pause: "pause",
    Qt.Key.Key_ScrollLock: "scrolllock",
    Qt.Key.Key_Menu: "apps",
}


def _modifier_names(modifiers: Qt.KeyboardModifier) -> list[str]:
    return [name for flag, name in _QT_MODIFIERS if modifiers & flag]


def chord_from_event(event: QKeyEvent) -> Chord | None:
    """押されたキーの組み合わせ。修飾キーだけ・対応していないキーなら None。"""
    if Qt.Key(event.key()) in _MODIFIER_KEYS:
        return None
    vk = event.nativeVirtualKey()
    name = key_name(vk) if vk else _QT_KEY_NAMES.get(Qt.Key(event.key()))
    if name is None:
        return None
    return parse_chord("+".join([*_modifier_names(event.modifiers()), name]))


class KeyCaptureEdit(QLineEdit):
    """クリックしてからキーを押すと、その組み合わせを表示する入力欄。"""

    chordChanged = Signal(object)  # Chord

    def __init__(self, chord: Chord) -> None:
        super().__init__(chord.display)
        self.chord = chord
        self.setReadOnly(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setPlaceholderText("キーの組み合わせを押してください")

    def event(self, event: QEvent) -> bool:
        # Tab をフォーカス移動に使わず、キーとして受け取る
        if event.type() == QEvent.Type.KeyPress and isinstance(event, QKeyEvent):
            self.keyPressEvent(event)
            return True
        return super().event(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        chord = chord_from_event(event)
        if chord is None:
            key = Qt.Key(event.key())
            if key in _MODIFIER_KEYS:
                held = {*_modifier_names(event.modifiers()), _MODIFIER_KEYS[key]}
                mods = [name for _, name in _QT_MODIFIERS if name in held]
                # 修飾キーだけを押している途中
                self.setText("+".join(m.capitalize() for m in mods) + "+…")
            else:
                self.setText("このキーは使えません")
            return
        self.chord = chord
        self.setText(chord.display)
        self.chordChanged.emit(chord)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        # 修飾キーだけ押して離したら、決まっているキーの表示に戻す
        if self.text().endswith("…") or self.text() == "このキーは使えません":
            self.setText(self.chord.display)


class SettingsDialog(QDialog):
    """よく変える項目だけを並べた設定画面。それ以外の項目は今の値のまま保存する。"""

    def __init__(
        self,
        cfg: Config,
        devices: Sequence[str],
        apply: Callable[[Config], str],  # 反映できなければエラーメッセージを返す
    ) -> None:
        super().__init__()
        self._cfg = cfg
        self._apply = apply
        self.setWindowTitle("kotoba-desktop の設定")
        self.setMinimumWidth(460)

        # 録音の開始 / 終了のキー
        self.key_edit = KeyCaptureEdit(cfg.hotkey.chord)
        key_note = _note(
            "入力欄をクリックしてから、使いたいキーの組み合わせを押してください。"
            "Win+H など Windows や他のアプリが使っているキーは選べません。"
        )

        # マイク
        self.device = QComboBox()
        self.device.addItem("既定のマイク", "")
        for name in devices:
            self.device.addItem(name, name)
        if cfg.audio.device and self.device.findData(cfg.audio.device) < 0:
            self.device.addItem(f"{cfg.audio.device}（見つかりません）", cfg.audio.device)
        self.device.setCurrentIndex(max(self.device.findData(cfg.audio.device), 0))
        self.keep_open = QCheckBox("マイクを開いたままにする（話し始めが欠けるとき）")
        self.keep_open.setChecked(cfg.audio.keep_open)
        self.keep_open.setToolTip(
            "押す直前 0.3 秒の音も録れます。タスクバーのマイク使用中の表示が出続けます"
        )

        # 入力
        self.punctuation = QComboBox()
        self.punctuation.addItem("モデルの出力のまま", "keep")
        self.punctuation.addItem("「、。」を除く", "strip")
        self.punctuation.setCurrentIndex(max(self.punctuation.findData(cfg.text.punctuation), 0))
        self.always_show = QCheckBox("ウィジェットを常に表示する")
        self.always_show.setChecked(cfg.widget.always_show)

        # 置換辞書
        self.replace = QTableWidget(0, 2)
        self.replace.setHorizontalHeaderLabels(["認識結果", "置き換え後"])
        self.replace.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.replace.verticalHeader().hide()
        self.replace.setMinimumHeight(140)
        for old, new in cfg.text.replace.items():
            self._add_row(old, new)
        add = QPushButton("追加")
        add.clicked.connect(lambda: self._add_row("", "", edit=True))
        remove = QPushButton("削除")
        remove.clicked.connect(self._remove_rows)
        replace_buttons = QHBoxLayout()
        replace_buttons.addWidget(add)
        replace_buttons.addWidget(remove)
        replace_buttons.addStretch()

        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color: #d13438;")
        self.error.hide()
        self.key_edit.chordChanged.connect(lambda _: self.error.hide())

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        # Enter を押してもダイアログを閉じず、キーの入力欄が Enter を受け取れるようにする
        for button in buttons.buttons():
            if isinstance(button, QPushButton):
                button.setAutoDefault(False)
                button.setDefault(False)

        form = QFormLayout()
        form.addRow("録音の開始 / 終了", self.key_edit)
        form.addRow("", key_note)
        form.addRow("マイク", self.device)
        form.addRow("", self.keep_open)
        form.addRow("句読点", self.punctuation)
        form.addRow("", self.always_show)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addSpacing(8)
        layout.addWidget(QLabel("<b>置換辞書</b>"))
        layout.addWidget(
            _note("認識結果に含まれる語を置き換えます（例: クロードコード → Claude Code）。")
        )
        layout.addWidget(self.replace)
        layout.addLayout(replace_buttons)
        layout.addWidget(self.error)
        layout.addWidget(buttons)
        self.key_edit.setFocus()

    def _add_row(self, old: str, new: str, *, edit: bool = False) -> None:
        row = self.replace.rowCount()
        self.replace.insertRow(row)
        self.replace.setItem(row, 0, QTableWidgetItem(old))
        self.replace.setItem(row, 1, QTableWidgetItem(new))
        if edit and (item := self.replace.item(row, 0)):
            self.replace.setCurrentCell(row, 0)
            self.replace.editItem(item)

    def _remove_rows(self) -> None:
        rows = sorted({i.row() for i in self.replace.selectedIndexes()}, reverse=True)
        for row in rows:
            self.replace.removeRow(row)

    def _replace_dict(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for row in range(self.replace.rowCount()):
            old_item, new_item = self.replace.item(row, 0), self.replace.item(row, 1)
            old = old_item.text() if old_item else ""
            if old:  # 「認識結果」が空の行は無視する
                result[old] = new_item.text() if new_item else ""
        return result

    def build_config(self) -> Config:
        """画面の内容を反映した設定。誤りがあれば ValueError。"""
        *modifiers, key = self.key_edit.chord.text.split("+")
        data = self._cfg.model_dump()
        data["hotkey"] = {"key": key, "modifiers": modifiers}
        data["audio"] |= {
            "device": self.device.currentData(),
            "keep_open": self.keep_open.isChecked(),
        }
        data["text"] |= {
            "punctuation": self.punctuation.currentData(),
            "replace": self._replace_dict(),
        }
        data["widget"] |= {"always_show": self.always_show.isChecked()}
        try:
            return Config.model_validate(data)
        except ValidationError as e:
            raise ValueError(
                "。".join(err["msg"].removeprefix("Value error, ") for err in e.errors())
            ) from e

    def _on_ok(self) -> None:
        try:
            message = self._apply(self.build_config())
        except ValueError as e:
            message = str(e)
        if message:
            self.error.setText(message)
            self.error.show()
            return
        self.accept()


def _note(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet("color: palette(placeholder-text);")
    return label
