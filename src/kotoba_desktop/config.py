"""設定ファイル（TOML）の読み込みと pydantic による検証。"""

import os
import re
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from kotoba_desktop.keys import Chord, parse_chord


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
        if "win" in chord.modifiers:
            raise ValueError("Win キーの組み合わせは OS 用なので使えません")
        if "alt" in chord.modifiers and "ctrl" not in chord.modifiers:
            # 主キーだけが飲み込まれ、入力先に Alt の押下と解放が届いてメニューバーが開く
            raise ValueError(
                "Alt を使うときは Ctrl と組み合わせてください（メニューバーが開くため）"
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
    model: str = "kotoba-tech/kotoba-whisper-v2.0-faster"
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


DEFAULT_TOML = """\
# kotoba-desktop の設定。保存後、トレイの「再読み込み」で反映される。

[hotkey]
key = "h"                 # Ctrl+H（押すたびに録音の開始 / 終了）
modifiers = ["ctrl"]      # ctrl / shift / alt

[audio]
device = ""               # 空 = OS の既定マイク。名前の一部で指定できる
keep_open = false         # 話し始めが欠けるなら true（開いたままにし、押す直前 0.3 秒も録る）
min_speech_ms = 300       # これより短い発話は認識しない
max_chunk_s = 15          # 長い発話はこの秒数以内に区切って認識する

[asr]
model = "kotoba-tech/kotoba-whisper-v2.0-faster"
compute_type = "float16"
beam_size = 1
hotwords = ""             # 認識させたい語を空白区切りで（例: "Claude Code Cursor WSL"）

[inject]
method = "paste"          # paste（貼り付け）| type（1 文字ずつ打鍵）
paste_key = "ctrl+v"
restore_delay_ms = 300    # 貼り付け後、元のクリップボードを戻すまでの待ち時間

[[inject.profile]]
match_process = "WindowsTerminal.exe"
paste_key = "shift+insert"

[[inject.profile]]
match_class = "ConsoleWindowClass"
paste_key = "shift+insert"

[text]
punctuation = "keep"      # keep（モデル出力のまま）| strip（「、。」を除去）
drop_phrases = ["ご視聴ありがとうございました", "チャンネル登録お願いします"]

[text.replace]
# "クロードコード" = "Claude Code"

[widget]
always_show = false
"""


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
    """設定ファイルを読む。無ければ既定値のファイルを作ってから読む。"""
    path = path or config_path()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_TOML, encoding="utf-8")
    return parse(path.read_text(encoding="utf-8"))


def _toml_value(value: str | bool) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def update_value(path: Path, section: str, key: str, value: str | bool) -> None:
    """設定ファイルの [section] の key だけを書き換える。コメントや他の行はそのまま残す。

    トレイのメニュー（マイク選択、ウィジェットを常に表示）から使う。
    """
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    literal = _toml_value(value)
    header = re.compile(rf"^\s*\[\s*{re.escape(section)}\s*\]\s*(#.*)?$")
    any_header = re.compile(r"^\s*\[")
    # 値は "..."（中の \" や \\ を含む）、'...'（リテラル文字列）、
    # 空白と # を含まない語（true、300 など）のどれか
    value_pattern = r""""(?:[^"\\]|\\.)*"|'[^']*'|[^#\s]+"""
    entry = re.compile(rf"^(\s*{re.escape(key)}\s*=\s*)({value_pattern})(.*)$", re.S)

    start = next((i for i, line in enumerate(lines) if header.match(line)), None)
    if start is None:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines += ["\n", f"[{section}]\n", f"{key} = {literal}\n"]
    else:
        end = next(
            (i for i in range(start + 1, len(lines)) if any_header.match(lines[i])), len(lines)
        )
        for i in range(start + 1, end):
            if m := entry.match(lines[i]):
                lines[i] = m.group(1) + literal + m.group(3)
                break
        else:
            lines.insert(start + 1, f"{key} = {literal}\n")
    text = "".join(lines)
    parse(text)  # 壊れた設定を書き込まない
    path.write_text(text, encoding="utf-8")
