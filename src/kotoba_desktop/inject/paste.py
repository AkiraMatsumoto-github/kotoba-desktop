"""クリップボード経由の貼り付けで入力する（設計書第 8 章の手順 5〜8）。"""

import logging
import time
from collections.abc import Callable

from kotoba_desktop.keys import Chord
from kotoba_desktop.win32 import clipboard
from kotoba_desktop.win32.input import send_chord

log = logging.getLogger(__name__)

# 文字列を置いてから貼り付けキーを送るまでの待ち時間
SETTLE_S = 0.05
# 入力先が貼り付けのためにクリップボードを開いたままのことがあるので、復元は長めに再試行する
RESTORE_RETRIES = 100


class TargetChanged(Exception):
    """貼り付けキーを送る直前に前面ウィンドウが変わった。元のクリップボードは戻してある。"""


def paste(
    text: str, key: Chord, restore_delay_ms: int, still_target: Callable[[], bool] = lambda: True
) -> str:
    """text を貼り付け、元のクリップボードを戻す。

    戻り値は補足（問題がなければ空）。貼り付けキーを送る前に失敗したときは、元のクリップボードを
    戻してから例外を出す（入力されていないので、呼び出し側はエラーとして扱える）。
    """
    saved = clipboard.snapshot()
    seq = clipboard.set_text(text)
    try:
        time.sleep(SETTLE_S)
        # 退避や待ちの間に前面ウィンドウが変わっていたら、合わない貼り付けキーを送らない
        if not still_target():
            raise TargetChanged
        send_chord(key)
        time.sleep(restore_delay_ms / 1000)
    finally:
        note = _restore(saved, seq)
    return note


def _restore(saved: clipboard.Snapshot, seq: int) -> str:
    # 自分が置いた後に誰かが書き換えていたら、その内容を消さないよう戻さない
    if clipboard.sequence_number() != seq:
        return "クリップボードが他のアプリに書き換えられたので元に戻していません"
    try:
        clipboard.restore(saved, retries=RESTORE_RETRIES)
    except OSError:
        log.warning("クリップボードを元に戻せません", exc_info=True)
        return "元のクリップボードを戻せませんでした"
    return ""
