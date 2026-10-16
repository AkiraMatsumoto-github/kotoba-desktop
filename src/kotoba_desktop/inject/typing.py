"""1 文字ずつ打鍵して入力する（予備の方式）。

IME が ON だとキー入力が未確定文字列に混ざるので、送る間だけ OFF にする。
"""

import time

from kotoba_desktop.win32 import ime
from kotoba_desktop.win32.input import send_unicode

CHUNK = 32  # この文字数ごとに少し間を空ける
PAUSE_S = 0.01


def type_text(hwnd: int, text: str) -> None:
    was_open = ime.is_open(hwnd)
    if was_open:
        ime.set_open(hwnd, False)
    sent = 0
    try:
        for i in range(0, len(text), CHUNK):
            send_unicode(text[i : i + CHUNK])
            sent = min(i + CHUNK, len(text))
            time.sleep(PAUSE_S)
    except OSError as e:
        # 送り済みの分は入力されているので、入れ直すと重複することを伝える
        raise OSError(f"{len(text)} 文字中 {sent} 文字を入力した後に失敗しました: {e}") from e
    finally:
        if was_open:
            ime.set_open(hwnd, True)
