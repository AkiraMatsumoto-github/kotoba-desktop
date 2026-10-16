"""入力の正確性を機械的に照合する（Phase 0 の P0-08〜P0-10）。

送信: 既知の文字列を、本番と同じ経路（Injector）で前面ウィンドウへ入力する。
    uv run python tools/inject_check.py send [--method paste|type] [--count 20] [--sep enter|none]
  実行後 5 秒以内に入力先をクリックしてカーソルを置く。送信中に前面ウィンドウが変わったら止まる。
  期待する文字列を tools/poc/out/expected.txt に 1 行 1 件で書く。

照合: 受信側が保存したファイルと比べ、不一致を表示する。
    uv run python tools/inject_check.py verify tools/poc/out/received.txt

受信側:
  WSL のターミナル（bash / Cursor の統合ターミナル）: python3 tools/poc/recv.py <保存先>
  Chrome: tools/poc/receiver.html を開き、終わったら「保存」
  Cursor のエディタ: 新しいファイルを開いて送信し、保存したファイルを照合する
"""

import argparse
import sys
import time
from pathlib import Path

from kotoba_desktop import config
from kotoba_desktop.inject.injector import Injector, Status
from kotoba_desktop.keys import parse_chord
from kotoba_desktop.win32.input import send_chord
from kotoba_desktop.win32.window import foreground

OUT = Path(__file__).parent / "poc" / "out"

_LONG = "".join(f"（{i:03}）音声入力の正確性を確かめるための長い文章です。" for i in range(1, 22))[
    :500
]

CASES = [
    "今日は良い天気ですね、明日も晴れるでしょう。",
    "ABC abc 0123456789 Hello World",
    "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~",
    "𠮷野家で🍣を食べた",
    "Claude Code で WSL の ls -la を実行する",
    "全角（括弧）と「かぎ括弧」、句読点。",
    _LONG,
]


def send(args: argparse.Namespace) -> None:
    cfg = config.load()
    if args.method:
        # プロファイル側の method も外して、全アプリで指定の方式を使う
        profiles = [p.model_copy(update={"method": None}) for p in cfg.inject.profile]
        inject = cfg.inject.model_copy(update={"method": args.method, "profile": profiles})
        cfg = cfg.model_copy(update={"inject": inject})
    injector = Injector(lambda: cfg, lambda r: None)
    separator = parse_chord("enter") if args.sep == "enter" else None

    for i in range(args.delay, 0, -1):
        print(f"{i} 秒後に送信します。入力先をクリックしてください…", flush=True)
        time.sleep(1)
    target = foreground()
    if target is None:
        sys.exit("前面ウィンドウがありません")
    print(f"送信先: {target.process_name}（{target.class_name}）方式: {cfg.inject.method}")

    expected: list[str] = []
    for round_ in range(args.count):
        for case in CASES:
            now = foreground()
            if now is None or now.hwnd != target.hwnd:
                print("前面ウィンドウが変わったので止めました")
                break
            result = injector.inject(case, processed=True)
            if result.status is not Status.INJECTED:
                print(f"入力できませんでした: {result.status.value} {result.detail}")
                break
            if separator:
                send_chord(separator)
            expected.append(case)
            time.sleep(args.interval)
        else:
            print(f"{round_ + 1}/{args.count} 回目を送信しました", flush=True)
            continue
        break

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "expected.txt"
    path.write_text("\n".join(expected) + "\n", encoding="utf-8")
    print(f"{len(expected)} 件送信しました。期待値: {path}")


def verify(args: argparse.Namespace) -> None:
    expected = (OUT / "expected.txt").read_text(encoding="utf-8").splitlines()
    raw = Path(args.received).read_text(encoding="utf-8")
    received = raw.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    while received and not received[-1]:
        received.pop()

    mismatches = 0
    for i in range(max(len(expected), len(received))):
        exp = expected[i] if i < len(expected) else "（なし）"
        got = received[i] if i < len(received) else "（なし）"
        if exp != got:
            mismatches += 1
            if mismatches <= 10:
                print(f"--- {i + 1} 件目が不一致")
                print(f"期待: {exp!r}")
                print(f"受信: {got!r}")
    print(f"期待 {len(expected)} 件、受信 {len(received)} 件、不一致 {mismatches} 件")
    sys.exit(1 if mismatches else 0)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = parser.add_subparsers(required=True)
    p = sub.add_parser("send", help="既知の文字列を前面ウィンドウへ入力する")
    p.add_argument("--method", choices=["paste", "type"], help="省略時は設定ファイルのとおり")
    p.add_argument("--count", type=int, default=20, help="全パターンを何周送るか")
    p.add_argument(
        "--sep", choices=["enter", "none"], default="enter", help="1 件ごとに Enter を送るか"
    )
    p.add_argument("--delay", type=int, default=5, help="送信開始までの秒数")
    p.add_argument("--interval", type=float, default=0.3, help="1 件ごとの間隔（秒）")
    p.set_defaults(func=send)
    v = sub.add_parser("verify", help="受信したファイルを照合する")
    v.add_argument("received")
    v.set_defaults(func=verify)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
