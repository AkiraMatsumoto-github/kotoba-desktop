"""RegisterHotKey の結合テスト（P0-14）。

実際にキーを送るので KOTOBA_INTEGRATION=1 のときだけ実行する。
キーを送るのは登録に成功したときだけなので、Ctrl+H が他のアプリに届くことはない。
"""

import os
import threading

import pytest

from kotoba_desktop.hotkey import HotkeyError, HotkeyListener
from kotoba_desktop.keys import parse_chord
from kotoba_desktop.win32.input import send_chord

pytestmark = pytest.mark.skipif(
    os.environ.get("KOTOBA_INTEGRATION") != "1", reason="KOTOBA_INTEGRATION=1 のときだけ実行"
)


def test_ctrl_h_is_delivered() -> None:
    # 他のアプリに届かない（飲み込まれる）ことは RegisterHotKey の仕様で、ここでは確かめない
    pressed = threading.Event()
    listener = HotkeyListener(parse_chord("ctrl+h"), pressed.set)
    listener.start()
    try:
        send_chord(parse_chord("ctrl+h"))
        assert pressed.wait(2)
    finally:
        listener.stop()


def test_duplicate_registration_fails() -> None:
    first = HotkeyListener(parse_chord("ctrl+alt+f11"), lambda: None)
    first.start()
    try:
        with pytest.raises(HotkeyError):
            HotkeyListener(parse_chord("ctrl+alt+f11"), lambda: None).start()
    finally:
        first.stop()


def test_stop_then_register_again() -> None:
    chord = parse_chord("ctrl+alt+f11")
    for _ in range(3):
        listener = HotkeyListener(chord, lambda: None)
        listener.start()
        listener.stop()
