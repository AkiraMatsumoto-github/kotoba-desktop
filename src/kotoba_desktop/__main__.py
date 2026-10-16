"""kotoba-desktop のエントリポイント。"""

import ctypes
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from kotoba_desktop.config import app_dir

log = logging.getLogger("kotoba_desktop")


def _message_box(text: str) -> None:
    ctypes.windll.user32.MessageBoxW(None, text, "kotoba-desktop", 0x40)  # MB_ICONINFORMATION


def _setup_logging() -> None:
    # 認識した文字列はログに書かない（プライバシー）。書くのは件数・文字数・時間だけ
    directory = app_dir()
    directory.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        directory / "kotoba-desktop.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    if os.environ.get("KOTOBA_DEBUG"):
        root.setLevel(logging.DEBUG)
        root.addHandler(logging.StreamHandler())


def main() -> None:
    """常駐アプリを起動する。"""
    # gui-scripts（pythonw）では標準出力が無く、進捗表示などを書くライブラリが落ちる
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    _setup_logging()

    from kotoba_desktop.win32 import instance

    if not instance.acquire():
        _message_box("kotoba-desktop は既に起動しています。タスクトレイを確認してください。")
        return

    try:
        from PySide6.QtWidgets import QApplication

        from kotoba_desktop.app import App

        qapp = QApplication(sys.argv)
        qapp.setApplicationName("kotoba-desktop")
        qapp.setQuitOnLastWindowClosed(False)
        app = App(qapp)  # noqa: F841  終了まで参照を保持する
        log.info("起動しました")
        code = qapp.exec()
    except Exception as e:
        log.exception("起動に失敗")
        _message_box(f"起動に失敗しました: {e}\nログ: {app_dir() / 'kotoba-desktop.log'}")
        sys.exit(1)
    sys.exit(code)


if __name__ == "__main__":
    main()
