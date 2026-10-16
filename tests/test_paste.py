"""貼り付け手順（退避 → 書き込み → 送信 → 更新番号の確認 → 復元）。

クリップボードとキー送信は差し替えるので、手元のクリップボードには触れない。
"""

from dataclasses import dataclass, field

import pytest

from kotoba_desktop.inject import paste as paste_mod
from kotoba_desktop.inject.paste import TargetChanged, paste
from kotoba_desktop.keys import Chord, parse_chord

CTRL_V = parse_chord("ctrl+v")


@dataclass
class FakeClipboard:
    content: list[tuple[int, bytes]] = field(default_factory=lambda: [(13, b"orig")])
    seq: int = 1
    log: list[str] = field(default_factory=list)
    restore_error: Exception | None = None
    send_error: Exception | None = None
    other_app_writes: bool = False  # 貼り付けの間に他のアプリが書き換える

    def snapshot(self) -> list[tuple[int, bytes]]:
        self.log.append("snapshot")
        return list(self.content)

    def set_text(self, text: str) -> int:
        self.log.append(f"set:{text}")
        self.content = [(13, text.encode())]
        self.seq += 1
        return self.seq

    def sequence_number(self) -> int:
        return self.seq

    def restore(self, saved: list[tuple[int, bytes]], retries: int = 20) -> None:
        self.log.append("restore")
        if self.restore_error:
            raise self.restore_error
        self.content = saved

    def send_chord(self, chord: Chord) -> None:
        if self.send_error:
            raise self.send_error
        self.log.append(f"send:{chord}")
        if self.other_app_writes:
            self.seq += 1


@pytest.fixture
def clip(monkeypatch: pytest.MonkeyPatch) -> FakeClipboard:
    fake = FakeClipboard()
    for name in ("snapshot", "set_text", "sequence_number", "restore"):
        monkeypatch.setattr(paste_mod.clipboard, name, getattr(fake, name))
    monkeypatch.setattr(paste_mod, "send_chord", fake.send_chord)
    monkeypatch.setattr(paste_mod, "SETTLE_S", 0)
    return fake


def test_paste_then_restore(clip: FakeClipboard) -> None:
    assert paste("認識", CTRL_V, 0) == ""
    assert clip.log == ["snapshot", "set:認識", "send:ctrl+v", "restore"]
    assert clip.content == [(13, b"orig")]


def test_not_restored_when_other_app_wrote(clip: FakeClipboard) -> None:
    clip.other_app_writes = True
    note = paste("認識", CTRL_V, 0)
    assert "書き換えられた" in note
    assert "restore" not in clip.log


def test_restore_failure_is_a_note_not_an_error(clip: FakeClipboard) -> None:
    clip.restore_error = OSError("busy")
    note = paste("認識", CTRL_V, 0)
    assert "戻せませんでした" in note
    assert "send:ctrl+v" in clip.log


def test_send_failure_restores_and_raises(clip: FakeClipboard) -> None:
    clip.send_error = OSError("SendInput")
    with pytest.raises(OSError, match="SendInput"):
        paste("認識", CTRL_V, 0)
    assert clip.log[-1] == "restore"
    assert clip.content == [(13, b"orig")]


def test_target_changed_restores_without_sending(clip: FakeClipboard) -> None:
    with pytest.raises(TargetChanged):
        paste("認識", CTRL_V, 0, still_target=lambda: False)
    assert not any(e.startswith("send:") for e in clip.log)
    assert clip.content == [(13, b"orig")]
