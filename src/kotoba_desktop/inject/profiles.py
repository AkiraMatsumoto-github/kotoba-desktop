"""前面ウィンドウから入力方法（貼り付けキーなど）を決める。"""

from dataclasses import dataclass

from kotoba_desktop.config import InjectConfig, InjectProfile
from kotoba_desktop.keys import Chord, parse_chord


@dataclass(frozen=True)
class Profile:
    method: str  # "paste" | "type"
    paste_key: Chord
    restore_delay_ms: int
    punctuation: str


def _matches(p: InjectProfile, process_name: str, class_name: str) -> bool:
    if p.match_process and p.match_process.casefold() != process_name.casefold():
        return False
    return not (p.match_class and p.match_class != class_name)


def resolve(config: InjectConfig, punctuation: str, process_name: str, class_name: str) -> Profile:
    """最初に一致したプロファイルの値で既定値を上書きする。"""
    profile = next((p for p in config.profile if _matches(p, process_name, class_name)), None)

    def pick[T](name: str, default: T) -> T:
        value = getattr(profile, name, None) if profile else None
        return default if value is None else value

    return Profile(
        method=pick("method", config.method),
        paste_key=parse_chord(pick("paste_key", config.paste_key)),
        restore_delay_ms=pick("restore_delay_ms", config.restore_delay_ms),
        punctuation=pick("punctuation", punctuation),
    )
