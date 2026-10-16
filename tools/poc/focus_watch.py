"""P0-13: 前面ウィンドウが変わるたびに表示する。

別のターミナルでこれを動かしたまま、kotoba-desktop のウィジェットをクリック・ドラッグする。
ウィジェットがフォーカスを奪っていなければ、何も表示されない（入力先のアプリのまま）。

    uv run python tools/poc/focus_watch.py [秒数]
"""

import sys
import time

from kotoba_desktop.win32.window import foreground


def main() -> None:
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 120
    last = None
    changes = 0
    deadline = time.monotonic() + seconds
    print(f"{seconds:.0f} 秒間、前面ウィンドウの変化を記録します")
    while time.monotonic() < deadline:
        win = foreground()
        key = win.hwnd if win else None
        if key != last:
            if last is not None:
                changes += 1
            label = f"{win.process_name}（{win.class_name}）" if win else "（なし）"
            print(f"{time.strftime('%H:%M:%S')} 前面: {label}", flush=True)
            last = key
        time.sleep(0.02)
    print(f"変化 {changes} 回")


if __name__ == "__main__":
    main()
