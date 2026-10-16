#!/usr/bin/env python3
"""WSL のターミナル側で、届いた入力をそのままファイルに書く（inject_check.py の受信側）。

標準入力を raw モードにするので、シェルや行編集を通さずに届いたバイト列を記録できる。
bracketed paste を有効にし、貼り付けの開始・終了の印は取り除く。Enter（CR）で 1 件の区切り。
Ctrl+D で終了する。WSL の python3（標準ライブラリだけ）で動く。

    python3 tools/poc/recv.py /mnt/c/Users/<you>/dev/kotoba-desktop/tools/poc/out/received.txt
"""

import os
import sys
import termios
import tty

PASTE_START = b"\x1b[200~"
PASTE_END = b"\x1b[201~"


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(f"使い方: {sys.argv[0]} <保存先>")
    path = sys.argv[1]
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    data = bytearray()
    lines = 0
    print("受信を待っています。送信が終わったら Ctrl+D で保存して終了します。\r")
    sys.stdout.write("\x1b[?2004h")  # bracketed paste を有効にする
    sys.stdout.flush()
    try:
        tty.setraw(fd)
        while True:
            chunk = os.read(fd, 65536)
            if not chunk or b"\x04" in chunk:
                data += chunk.split(b"\x04", 1)[0]
                break
            data += chunk
            if (n := data.count(b"\r")) != lines:
                lines = n
                sys.stdout.write(f"\r{lines} 件受信")
                sys.stdout.flush()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)
        sys.stdout.write("\x1b[?2004l\n")
    text = data.replace(PASTE_START, b"").replace(PASTE_END, b"").decode("utf-8", "replace")
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text.replace("\r", "\n"))
    print(f"{lines} 件を {path} に保存しました")


if __name__ == "__main__":
    main()
