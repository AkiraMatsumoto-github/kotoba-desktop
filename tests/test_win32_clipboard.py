"""実際のクリップボードを使う結合テスト。

手元のクリップボードを一時的に書き換えるので、KOTOBA_INTEGRATION=1 のときだけ実行する。
"""

import os

import pytest

from kotoba_desktop.win32 import clipboard

pytestmark = pytest.mark.skipif(
    os.environ.get("KOTOBA_INTEGRATION") != "1", reason="KOTOBA_INTEGRATION=1 のときだけ実行"
)


@pytest.fixture(autouse=True)
def keep_user_clipboard():
    saved = clipboard.snapshot()
    yield
    clipboard.restore(saved)


def test_set_and_get_text_with_surrogates() -> None:
    text = "日本語 ABC 123 !@# 𠮷野家"
    seq_before = clipboard.sequence_number()
    seq = clipboard.set_text(text)
    assert seq != seq_before
    assert clipboard.get_text() == text


def test_snapshot_restore_roundtrip() -> None:
    clipboard.set_text("元の内容")
    saved = clipboard.snapshot()
    clipboard.set_text("認識結果")
    clipboard.restore(saved)
    assert clipboard.get_text() == "元の内容"


def test_restore_empty_clears() -> None:
    clipboard.set_text("消える")
    clipboard.restore([])
    assert clipboard.get_text() is None


def test_exclusion_formats_present() -> None:
    import ctypes

    clipboard.set_text("履歴に残らない")
    fmt = clipboard.user32.RegisterClipboardFormatW("ExcludeClipboardContentFromMonitorProcessing")
    assert ctypes.windll.user32.IsClipboardFormatAvailable(fmt)


def test_image_survives_roundtrip() -> None:
    """P0-11: 画像（CF_DIB）をコピーした状態で入力しても、元の画像に戻る。"""
    cf_dib = 8
    header = (40).to_bytes(4, "little") + (2).to_bytes(4, "little") + (2).to_bytes(4, "little")
    header += (1).to_bytes(2, "little") + (32).to_bytes(2, "little") + bytes(24)
    pixels = bytes([255, 0, 0, 255, 0, 255, 0, 255, 0, 0, 255, 255, 255, 255, 255, 255])
    with clipboard._opened():
        clipboard.user32.EmptyClipboard()
        clipboard._set_bytes(cf_dib, header + pixels)
    saved = clipboard.snapshot()
    clipboard.set_text("認識結果")
    clipboard.restore(saved)
    restored = dict(clipboard.snapshot())
    assert restored[cf_dib][: len(header + pixels)] == header + pixels
