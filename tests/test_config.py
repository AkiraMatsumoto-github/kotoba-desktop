from pathlib import Path

import pytest

from kotoba_desktop import config
from kotoba_desktop.config import ConfigError


def test_defaults() -> None:
    cfg = config.parse("")
    assert str(cfg.hotkey.chord) == "ctrl+h"
    assert cfg.inject.paste_key == "ctrl+v"
    assert [p.match_process for p in cfg.inject.profile] == ["WindowsTerminal.exe", None]


def test_load_creates_default_file(tmp_path: Path) -> None:
    path = tmp_path / "sub" / "config.toml"
    cfg = config.load(path)
    assert cfg == config.Config()
    assert path.read_text(encoding="utf-8").startswith("# kotoba-desktop の設定")


def test_error_names_the_field() -> None:
    with pytest.raises(ConfigError) as e:
        config.parse('[inject]\npaste_key = "ctrl+foo"\n')
    assert "inject.paste_key" in str(e.value)


def test_unknown_key_is_error() -> None:
    with pytest.raises(ConfigError) as e:
        config.parse("[audio]\ndevise = 'x'\n")
    assert "audio.devise" in str(e.value)


@pytest.mark.parametrize(
    ("key", "modifiers", "display"),
    [("h", '["win", "alt"]', "Win+Alt+H"), ("space", '["alt"]', "Alt+Space"), ("f9", "[]", "F9")],
)
def test_win_and_alt_combinations_allowed(key: str, modifiers: str, display: str) -> None:
    cfg = config.parse(f'[hotkey]\nkey = "{key}"\nmodifiers = {modifiers}\n')
    assert cfg.hotkey.chord.display == display


@pytest.mark.parametrize(("key", "modifiers"), [("a", "[]"), ("space", "[]"), ("1", '["shift"]')])
def test_typing_keys_alone_rejected(key: str, modifiers: str) -> None:
    with pytest.raises(ConfigError, match="普段の入力"):
        config.parse(f'[hotkey]\nkey = "{key}"\nmodifiers = {modifiers}\n')


def test_profile_needs_match() -> None:
    with pytest.raises(ConfigError, match="match_process"):
        config.parse('[[inject.profile]]\npaste_key = "ctrl+v"\n')


def test_broken_toml() -> None:
    with pytest.raises(ConfigError, match="TOML"):
        config.parse("[hotkey")


def test_save_roundtrip_with_tricky_values(tmp_path: Path) -> None:
    cfg = config.Config.model_validate(
        {
            "hotkey": {"key": "h", "modifiers": ["win", "alt"]},
            "audio": {"device": 'マイク "C960"', "keep_open": True},
            "text": {
                "punctuation": "strip",
                "replace": {'クロード "コード"': "a\\b", "改\n行": "", "タブ\t": "x"},
            },
            "inject": {"profile": []},
        }
    )
    path = tmp_path / "sub" / "config.toml"
    config.save(cfg, path)
    assert config.load(path) == cfg


def test_save_keeps_profiles(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    config.save(config.Config(), path)
    text = path.read_text(encoding="utf-8")
    assert "[[inject.profile]]" in text
    assert config.load(path).inject.profile == config.Config().inject.profile
