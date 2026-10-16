from pathlib import Path

import pytest

from kotoba_desktop import config
from kotoba_desktop.config import ConfigError


def test_default_toml_matches_defaults() -> None:
    assert config.parse(config.DEFAULT_TOML) == config.Config()


def test_defaults() -> None:
    cfg = config.parse("")
    assert str(cfg.hotkey.chord) == "ctrl+h"
    assert cfg.inject.paste_key == "ctrl+v"
    assert [p.match_process for p in cfg.inject.profile] == ["WindowsTerminal.exe", None]


def test_load_creates_default_file(tmp_path: Path) -> None:
    path = tmp_path / "sub" / "config.toml"
    cfg = config.load(path)
    assert path.read_text(encoding="utf-8") == config.DEFAULT_TOML
    assert cfg == config.Config()


def test_error_names_the_field() -> None:
    with pytest.raises(ConfigError) as e:
        config.parse('[inject]\npaste_key = "ctrl+foo"\n')
    assert "inject.paste_key" in str(e.value)


def test_unknown_key_is_error() -> None:
    with pytest.raises(ConfigError) as e:
        config.parse("[audio]\ndevise = 'x'\n")
    assert "audio.devise" in str(e.value)


def test_win_hotkey_rejected() -> None:
    with pytest.raises(ConfigError, match="Win"):
        config.parse('[hotkey]\nkey = "h"\nmodifiers = ["win"]\n')


def test_alt_without_ctrl_rejected() -> None:
    with pytest.raises(ConfigError, match="Alt"):
        config.parse('[hotkey]\nkey = "space"\nmodifiers = ["alt"]\n')
    config.parse('[hotkey]\nkey = "space"\nmodifiers = ["ctrl", "alt"]\n')


def test_profile_needs_match() -> None:
    with pytest.raises(ConfigError, match="match_process"):
        config.parse('[[inject.profile]]\npaste_key = "ctrl+v"\n')


def test_broken_toml() -> None:
    with pytest.raises(ConfigError, match="TOML"):
        config.parse("[hotkey")


def test_update_value_keeps_comments(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(config.DEFAULT_TOML, encoding="utf-8")
    config.update_value(path, "audio", "device", 'マイク "C960"')
    config.update_value(path, "widget", "always_show", True)
    text = path.read_text(encoding="utf-8")
    assert 'device = "マイク \\"C960\\""               # 空 = OS の既定マイク' in text
    assert "always_show = true" in text
    cfg = config.load(path)
    assert cfg.audio.device == 'マイク "C960"'
    assert cfg.widget.always_show is True
    # 他のセクションの同名キーは書き換えない
    assert 'model = "kotoba-tech/kotoba-whisper-v2.0-faster"' in text


def test_update_value_adds_missing_section_and_key(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[audio]\nmin_speech_ms = 200\n[hotkey]\nkey = "j"\n', encoding="utf-8")
    config.update_value(path, "audio", "device", "USB")
    config.update_value(path, "widget", "always_show", False)
    cfg = config.load(path)
    assert (cfg.audio.device, cfg.audio.min_speech_ms, cfg.hotkey.key) == ("USB", 200, "j")
    assert cfg.widget.always_show is False
