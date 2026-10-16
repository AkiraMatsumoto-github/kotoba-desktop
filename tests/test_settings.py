from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from kotoba_desktop.config import Config
from kotoba_desktop.keys import parse_chord
from kotoba_desktop.ui.settings import SettingsDialog

CTRL = Qt.KeyboardModifier.ControlModifier
ALT = Qt.KeyboardModifier.AltModifier
META = Qt.KeyboardModifier.MetaModifier

DEVICES = ["マイク (EMEET SmartCam C960)", "マイク (USB Audio)"]


def make(qtbot: QtBot, cfg: Config | None = None, apply=lambda cfg: "") -> SettingsDialog:
    dialog = SettingsDialog(cfg or Config(), DEVICES, apply)
    qtbot.addWidget(dialog)
    return dialog


def test_shows_current_values(qtbot: QtBot) -> None:
    cfg = Config.model_validate(
        {
            "audio": {"device": DEVICES[1], "keep_open": True},
            "text": {"punctuation": "strip", "replace": {"クロードコード": "Claude Code"}},
            "widget": {"always_show": True},
        }
    )
    d = make(qtbot, cfg)
    assert d.key_edit.text() == "Ctrl+H"
    assert d.device.currentData() == DEVICES[1]
    assert d.keep_open.isChecked()
    assert d.punctuation.currentData() == "strip"
    assert d.always_show.isChecked()
    assert d.replace.rowCount() == 1
    assert d.build_config() == cfg  # 何も変えなければ同じ設定になる


def test_missing_device_is_kept(qtbot: QtBot) -> None:
    d = make(qtbot, Config.model_validate({"audio": {"device": "外したマイク"}}))
    assert d.device.currentData() == "外したマイク"
    assert "見つかりません" in d.device.currentText()


def test_captures_combination(qtbot: QtBot) -> None:
    edit = make(qtbot).key_edit
    qtbot.keyClick(edit, Qt.Key.Key_K, CTRL | ALT)
    assert edit.text() == "Ctrl+Alt+K"
    assert edit.chord == parse_chord("ctrl+alt+k")


def test_captures_win_combination(qtbot: QtBot) -> None:
    edit = make(qtbot).key_edit
    qtbot.keyClick(edit, Qt.Key.Key_H, META | ALT)
    assert edit.text() == "Win+Alt+H"


def test_modifier_only_shows_progress_then_restores(qtbot: QtBot) -> None:
    edit = make(qtbot).key_edit
    qtbot.keyPress(edit, Qt.Key.Key_Control, CTRL)
    assert edit.text() == "Ctrl+…"
    qtbot.keyRelease(edit, Qt.Key.Key_Control)
    assert edit.text() == "Ctrl+H"


def test_tab_is_captured_not_focus_move(qtbot: QtBot) -> None:
    edit = make(qtbot).key_edit
    qtbot.keyClick(edit, Qt.Key.Key_Tab, CTRL)
    assert edit.text() == "Ctrl+Tab"


def test_build_config_reflects_changes(qtbot: QtBot) -> None:
    d = make(qtbot)
    qtbot.keyClick(d.key_edit, Qt.Key.Key_H, META | ALT)
    d.device.setCurrentIndex(1)
    d.keep_open.setChecked(True)
    d.punctuation.setCurrentIndex(1)
    d._add_row("クロードコード", "Claude Code")
    d._add_row("", "空の行は無視")
    cfg = d.build_config()
    assert cfg.hotkey.chord.display == "Win+Alt+H"
    assert (cfg.audio.device, cfg.audio.keep_open) == (DEVICES[0], True)
    assert cfg.text.punctuation == "strip"
    assert cfg.text.replace == {"クロードコード": "Claude Code"}
    # 画面に無い項目は元のまま
    assert cfg.inject == Config().inject


def test_remove_rows(qtbot: QtBot) -> None:
    d = make(qtbot, Config.model_validate({"text": {"replace": {"a": "1", "b": "2"}}}))
    d.replace.selectRow(0)
    d._remove_rows()
    assert d.build_config().text.replace == {"b": "2"}


def test_ok_applies_and_closes(qtbot: QtBot) -> None:
    applied: list[Config] = []
    d = make(qtbot, apply=lambda cfg: applied.append(cfg) or "")
    qtbot.keyClick(d.key_edit, Qt.Key.Key_F9)
    d._on_ok()
    assert applied[0].hotkey.chord.display == "F9"
    assert d.result() == SettingsDialog.DialogCode.Accepted


def test_invalid_key_shows_error(qtbot: QtBot) -> None:
    applied: list[Config] = []
    d = make(qtbot, apply=lambda cfg: applied.append(cfg) or "")
    d.show()
    qtbot.keyClick(d.key_edit, Qt.Key.Key_A)  # A だけでは普段の入力ができなくなる
    d._on_ok()
    assert applied == []
    assert d.isVisible()
    assert "普段の入力" in d.error.text()


def test_apply_error_keeps_dialog_open(qtbot: QtBot) -> None:
    d = make(qtbot, apply=lambda cfg: "Win+H は Windows か他のアプリが使っているため登録できません")
    d.show()
    d._on_ok()
    assert d.isVisible()
    assert "登録できません" in d.error.text()
