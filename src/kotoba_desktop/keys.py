"""キーの組み合わせ（"ctrl+h" など）の解析と仮想キーコードの対応表。

ホットキーの登録、貼り付けキーの送信、設定の検証で共通に使う。Win32 には依存しない。
"""

from dataclasses import dataclass

# 修飾キー名 → 仮想キーコード（送信用は左側のキーを使う）。並びは表記の順（Win+Ctrl+Alt+Shift）
MODIFIER_VK = {
    "win": 0x5B,  # VK_LWIN
    "ctrl": 0x11,  # VK_CONTROL
    "alt": 0x12,  # VK_MENU
    "shift": 0x10,  # VK_SHIFT
}

# RegisterHotKey の修飾フラグ
MODIFIER_FLAG = {"alt": 0x1, "ctrl": 0x2, "shift": 0x4, "win": 0x8}

_NAMED_VK = {
    "backspace": 0x08,
    "tab": 0x09,
    "enter": 0x0D,
    "pause": 0x13,
    "capslock": 0x14,
    "convert": 0x1C,  # 変換
    "nonconvert": 0x1D,  # 無変換
    "esc": 0x1B,
    "space": 0x20,
    "pageup": 0x21,
    "pagedown": 0x22,
    "end": 0x23,
    "home": 0x24,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "insert": 0x2D,
    "delete": 0x2E,
    "apps": 0x5D,
    "scrolllock": 0x91,
}
_NAMED_VK |= {chr(c).lower(): c for c in range(ord("A"), ord("Z") + 1)}
_NAMED_VK |= {chr(c): c for c in range(ord("0"), ord("9") + 1)}
_NAMED_VK |= {f"f{n}": 0x6F + n for n in range(1, 25)}  # VK_F1 = 0x70

_ALIASES = {"control": "ctrl", "menu": "alt", "return": "enter", "escape": "esc", "ins": "insert"}

_VK_NAME = {vk: name for name, vk in _NAMED_VK.items()}

# 単独（または Shift だけと組み合わせて）ホットキーにすると、普段の文字入力や操作ができなくなるキー
TYPING_KEYS = frozenset(
    {
        *(chr(c) for c in range(ord("a"), ord("z") + 1)),
        *(chr(c) for c in range(ord("0"), ord("9") + 1)),
        "space", "enter", "tab", "backspace", "esc", "delete", "insert",
        "left", "right", "up", "down", "home", "end", "pageup", "pagedown",
    }
)  # fmt: skip


def key_name(vk: int) -> str | None:
    """仮想キーコードからキー名（"h"、"f5" など）。対応していないキーは None。"""
    return _VK_NAME.get(vk)


# 拡張キー（KEYEVENTF_EXTENDEDKEY が必要）。付けないとテンキー側のキーとして扱われる
EXTENDED_VK = frozenset(
    {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x5B, 0x5C, 0x5D}
)


@dataclass(frozen=True)
class Chord:
    """修飾キーと 1 つの主キーの組み合わせ。"""

    modifiers: tuple[str, ...]  # MODIFIER_VK のキー名。並びは win, ctrl, alt, shift の順
    vk: int
    text: str  # 正規化した表記（例: "ctrl+h"）

    @property
    def hotkey_flags(self) -> int:
        flags = 0
        for m in self.modifiers:
            flags |= MODIFIER_FLAG[m]
        return flags

    def key_events(self) -> list[tuple[int, bool]]:
        """(仮想キーコード, 解放か) の列。

        修飾キーを押し、主キーを押して離し、修飾キーを逆順に離す。
        """
        mods = [MODIFIER_VK[m] for m in self.modifiers]
        return (
            [(vk, False) for vk in mods]
            + [(self.vk, False), (self.vk, True)]
            + [(vk, True) for vk in reversed(mods)]
        )

    @property
    def display(self) -> str:
        """画面に出す表記（例: "Ctrl+H"、"Shift+Insert"）。"""
        return "+".join(
            p.upper() if len(p) == 1 or (p[0] == "f" and p[1:].isdigit()) else p.capitalize()
            for p in self.text.split("+")
        )

    def __str__(self) -> str:
        return self.text


def parse_chord(text: str) -> Chord:
    """ "ctrl+h" や "Shift+Insert" を Chord にする。解釈できなければ ValueError。"""
    parts = [p.strip().lower() for p in text.split("+")]
    if not parts or any(not p for p in parts):
        raise ValueError(f"キーの書き方が正しくありません: {text!r}")
    parts = [_ALIASES.get(p, p) for p in parts]
    *mods, key = parts
    for m in mods:
        if m not in MODIFIER_VK:
            raise ValueError(f"修飾キーとして使えません: {m!r}（ctrl / shift / alt / win）")
    if len(set(mods)) != len(mods):
        raise ValueError(f"修飾キーが重複しています: {text!r}")
    if key in MODIFIER_VK:
        raise ValueError(f"修飾キーだけでは指定できません: {text!r}")
    if key not in _NAMED_VK:
        raise ValueError(f"知らないキー名です: {key!r}")
    ordered = tuple(m for m in MODIFIER_VK if m in mods)
    return Chord(ordered, _NAMED_VK[key], "+".join([*ordered, key]))
