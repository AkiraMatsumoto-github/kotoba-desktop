"""設定ファイル（TOML）の読み込みと pydantic による検証。"""

import json
import os
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from kotoba_desktop.keys import TYPING_KEYS, Chord, key_name, parse_chord


def app_dir() -> Path:
    """設定や状態を置くディレクトリ（%APPDATA%\\kotoba-desktop）。"""
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(base) / "kotoba-desktop"


def config_path() -> Path:
    return app_dir() / "config.toml"


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _check_chord(value: str) -> str:
    parse_chord(value)
    return value


class HotkeyConfig(_Section):
    key: str = "h"
    modifiers: list[Literal["ctrl", "shift", "alt", "win"]] = ["ctrl"]

    @model_validator(mode="after")
    def _valid_chord(self) -> HotkeyConfig:
        chord = self.chord
        # Win や Alt を含む組み合わせも使える。押したときにスタートメニューやメニューバーが
        # 開かないよう、hotkey.py がダミーのキーを送る。Win+H など OS が使うキーは登録時に失敗する
        if chord.modifiers in ((), ("shift",)) and key_name(chord.vk) in TYPING_KEYS:
            raise ValueError(
                f"{chord.display} だけでは普段の入力ができなくなります。"
                "Ctrl などと組み合わせてください"
            )
        if not chord.modifiers and chord.vk == 0x7B:
            raise ValueError("F12 は OS 予約なので使えません")
        return self

    @property
    def chord(self) -> Chord:
        return parse_chord("+".join([*self.modifiers, self.key]))


class AudioConfig(_Section):
    device: str = ""  # 空 = OS の既定マイク。名前の一部で指定する
    keep_open: bool = False  # マイクを開いたままにして、押す直前の音も録る
    min_speech_ms: int = Field(300, ge=0)
    max_chunk_s: float = Field(15.0, gt=1.0, le=28.0)


class AsrConfig(_Section):
    # 誤りが kotoba-whisper v2.0 の約半分だったので既定にした（設計書 第 4 章）
    model: str = "mobiuslabsgmbh/faster-whisper-large-v3-turbo"
    device: Literal["cuda", "cpu"] = "cuda"
    compute_type: str = "float16"
    beam_size: int = Field(1, ge=1, le=10)
    hotwords: str = ""
    no_speech_threshold: float = Field(0.6, ge=0.0, le=1.0)


Punctuation = Literal["keep", "strip"]
InjectMethod = Literal["paste", "type"]


class InjectProfile(_Section):
    """前面ウィンドウに応じて入力方法を変える設定。

    match_process と match_class の両方を書くと、両方に一致したときだけ使う。
    """

    match_process: str | None = None  # 例: "WindowsTerminal.exe"（大文字小文字は区別しない）
    match_class: str | None = None  # 例: "ConsoleWindowClass"
    method: InjectMethod | None = None
    paste_key: str | None = None
    restore_delay_ms: int | None = Field(None, ge=0, le=5000)
    punctuation: Punctuation | None = None

    @model_validator(mode="after")
    def _has_match(self) -> InjectProfile:
        if not self.match_process and not self.match_class:
            raise ValueError("match_process か match_class のどちらかが必要です")
        return self

    @field_validator("paste_key")
    @classmethod
    def _valid_key(cls, v: str | None) -> str | None:
        return None if v is None else _check_chord(v)


def _default_profiles() -> list[InjectProfile]:
    return [
        InjectProfile(match_process="WindowsTerminal.exe", paste_key="shift+insert"),
        InjectProfile(match_class="ConsoleWindowClass", paste_key="shift+insert"),
    ]


class InjectConfig(_Section):
    method: InjectMethod = "paste"
    paste_key: str = "ctrl+v"
    restore_delay_ms: int = Field(300, ge=0, le=5000)
    profile: list[InjectProfile] = Field(default_factory=_default_profiles)

    @field_validator("paste_key")
    @classmethod
    def _valid_key(cls, v: str) -> str:
        return _check_chord(v)


class TextConfig(_Section):
    punctuation: Punctuation = "keep"
    drop_phrases: list[str] = ["ご視聴ありがとうございました", "チャンネル登録お願いします"]
    replace: dict[str, str] = {}


class WidgetConfig(_Section):
    always_show: bool = False


class Config(_Section):
    hotkey: HotkeyConfig = HotkeyConfig()
    audio: AudioConfig = AudioConfig()
    asr: AsrConfig = AsrConfig()
    inject: InjectConfig = InjectConfig()
    text: TextConfig = TextConfig()
    widget: WidgetConfig = WidgetConfig()


class ConfigError(Exception):
    """設定ファイルの誤り。メッセージはそのまま通知に出せる形にする。"""


def _format_errors(err: ValidationError) -> str:
    lines = []
    for e in err.errors():
        where = ".".join(str(p) for p in e["loc"]) or "(全体)"
        msg = e["msg"].removeprefix("Value error, ")
        lines.append(f"{where}: {msg}")
    return "設定ファイルに誤りがあります\n" + "\n".join(lines)


def parse(text: str) -> Config:
    """TOML 文字列を検証して Config にする。誤りは ConfigError。"""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"設定ファイルを TOML として読めません: {e}") from e
    try:
        return Config.model_validate(data)
    except ValidationError as e:
        raise ConfigError(_format_errors(e)) from e


def load(path: Path | None = None) -> Config:
    """設定ファイルを読む。無ければ既定値で作ってから読む。"""
    path = path or config_path()
    if not path.exists():
        save(Config(), path)
    return parse(path.read_text(encoding="utf-8"))


_HEADER = """# kotoba-desktop の設定。
# よく変える項目はトレイの「設定…」で変えられる。設定画面に無い項目だけ、ここを直接編集する
# （編集後はアプリを再起動する）。
"""


def _value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, str):
        # JSON の文字列のエスケープは TOML の基本文字列としてもそのまま使える
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ", ".join(_value(v) for v in value) + "]"
    raise TypeError(f"TOML にできない値です: {value!r}")


def to_toml(cfg: Config) -> str:
    """Config を TOML の文字列にする。"""
    lines = [_HEADER]
    for section, data in cfg.model_dump(exclude_none=True).items():
        tables: list[str] = []
        lines.append(f"[{section}]")
        for key, value in data.items():
            if isinstance(value, dict):  # [text.replace] のような表
                tables += ["", f"[{section}.{key}]"]
                tables += [f"{_value(k)} = {_value(v)}" for k, v in value.items()]
            elif isinstance(value, list) and value and isinstance(value[0], dict):
                for item in value:  # [[inject.profile]] のような表の配列
                    tables += ["", f"[[{section}.{key}]]"]
                    tables += [f"{k} = {_value(v)}" for k, v in item.items()]
            else:
                lines.append(f"{key} = {_value(value)}")
        lines += [*tables, ""]
    return "\n".join(lines)


def save(cfg: Config, path: Path | None = None) -> None:
    """設定ファイルに書き出す。読み戻して同じ内容になることを確かめてから書く。"""
    path = path or config_path()
    text = to_toml(cfg)
    if parse(text) != cfg:
        raise ConfigError("設定を正しく書き出せませんでした")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
