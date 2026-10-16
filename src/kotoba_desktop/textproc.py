"""認識結果の後処理（禁止フレーズ、改行除去、置換辞書、句読点）。"""

import re
import unicodedata
from collections.abc import Mapping, Sequence

_FULLWIDTH_ALNUM = re.compile(r"[\uff10-\uff19\uff21-\uff3a\uff41-\uff5a]+")  # 全角英数字
_NEWLINES = re.compile(r"[\r\n\u2028\u2029]+")
_PUNCTUATION = str.maketrans("", "", "、。")
_TRAILING = "。.!！?？"  # noqa: RUF001
# 置換辞書に書かれた改行やタブ、NUL などの制御文字。ターミナルで Enter や補完として働くので必ず除く
_CONTROL = re.compile(r"[\x00-\x1f\x7f\u2028\u2029]")


def _halfwidth_alnum(text: str) -> str:
    return _FULLWIDTH_ALNUM.sub(lambda m: unicodedata.normalize("NFKC", m.group()), text)


def _is_drop_phrase(text: str, drop_phrases: Sequence[str]) -> bool:
    core = text.strip().rstrip(_TRAILING)
    return any(core == p.strip().rstrip(_TRAILING) for p in drop_phrases if p.strip())


def process(
    text: str,
    *,
    drop_phrases: Sequence[str] = (),
    replace: Mapping[str, str] | None = None,
    punctuation: str = "keep",
) -> str:
    """設計書第 8 章の順に後処理をかける。入力しないときは空文字を返す。"""
    # 1. 出力全体が禁止フレーズなら入力しない（ハルシネーション対策）
    if _is_drop_phrase(text, drop_phrases):
        return ""
    # 2. 改行を除き（Enter を送らない）、前後の空白を切る
    text = _NEWLINES.sub("", text).strip()
    # 3. 全角英数字を半角にする
    text = _halfwidth_alnum(text)
    # 4. 置換辞書を上から順に適用する
    for old, new in (replace or {}).items():
        if old:
            text = text.replace(old, new)
    # 5. 句読点
    if punctuation == "strip":
        text = text.translate(_PUNCTUATION)
    # 6. 制御文字を除く（置換辞書から入ったものも含め、最後に必ずかける）
    return _CONTROL.sub("", text).strip()
