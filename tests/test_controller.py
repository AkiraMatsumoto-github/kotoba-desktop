from dataclasses import dataclass, field

import numpy as np
import pytest
from pytestqt.qtbot import QtBot

from kotoba_desktop.controller import Controller, State
from kotoba_desktop.inject.injector import Result, Status
from kotoba_desktop.recognizer import Recognition


@dataclass
class FakeRecorder:
    level: float = 0.0
    started: int = 0
    stopped: int = 0
    cancelled: int = 0
    fail: Exception | None = None
    stop_fail: Exception | None = None

    def start(self) -> None:
        if self.fail:
            raise self.fail
        self.started += 1

    def stop(self) -> np.ndarray:
        if self.stop_fail:
            raise self.stop_fail
        self.stopped += 1
        return np.ones(16000, dtype=np.float32)

    def cancel(self) -> None:
        self.cancelled += 1


@dataclass
class FakeRecognizer:
    audio: list[np.ndarray] = field(default_factory=list)

    def submit(self, audio: np.ndarray) -> None:
        self.audio.append(audio)


@dataclass
class FakeInjector:
    texts: list[tuple[str, bool]] = field(default_factory=list)
    targets: list[int | None] = field(default_factory=list)

    def submit(self, text: str, *, processed: bool = False, target: int | None = None) -> None:
        self.texts.append((text, processed))
        self.targets.append(target)


@pytest.fixture
def parts(qtbot: QtBot) -> tuple[Controller, FakeRecorder, FakeRecognizer, FakeInjector]:
    rec, asr, inj = FakeRecorder(), FakeRecognizer(), FakeInjector()
    c = Controller(rec, asr, inj, "ctrl+h")
    c.post_loaded("")
    qtbot.waitUntil(lambda: c.current == State.IDLE)
    return c, rec, asr, inj


def test_starts_loading(qtbot: QtBot) -> None:
    c = Controller(FakeRecorder(), FakeRecognizer(), FakeInjector())
    assert c.current == State.LOADING
    c.toggle()
    assert c.current == State.LOADING


def test_load_failure(qtbot: QtBot) -> None:
    c = Controller(FakeRecorder(), FakeRecognizer(), FakeInjector())
    with qtbot.waitSignal(c.notify):
        c.post_loaded("モデルを読み込めません")
    assert c.current == State.FAILED


def test_full_cycle(qtbot: QtBot, parts) -> None:
    c, rec, asr, inj = parts
    c.toggle()
    assert c.current == State.RECORDING
    assert c.bubble == "準備中…"
    c.post_mic_ready()
    qtbot.waitUntil(lambda: c.bubble == "聞き取り中…")

    c.toggle()
    assert c.current == State.RECOGNIZING
    assert rec.stopped == 1 and len(asr.audio) == 1

    c.post_recognized(Recognition("こんにちは", 0.2))
    qtbot.waitUntil(lambda: c.current == State.INJECTING)
    assert inj.texts == [("こんにちは", False)]

    c.post_inject_result(Result("こんにちは", Status.INJECTED))
    qtbot.waitUntil(lambda: c.current == State.IDLE)
    assert c.bubble == "こんにちは"
    assert list(c.history) == ["こんにちは"]


def test_presses_ignored_while_busy(parts) -> None:
    c, rec, asr, _ = parts
    c.toggle()
    c.toggle()
    c.toggle()  # 認識中の押下は無視
    assert c.current == State.RECOGNIZING
    assert rec.started == 1 and len(asr.audio) == 1


def test_empty_recognition_returns_to_idle(qtbot: QtBot, parts) -> None:
    c, _, _, inj = parts
    c.toggle()
    c.toggle()
    c.post_recognized(Recognition("", 0.1))
    qtbot.waitUntil(lambda: c.current == State.IDLE)
    assert c.bubble == "聞き取れませんでした"
    assert inj.texts == []


def test_recorder_error_stays_idle(qtbot: QtBot, parts) -> None:
    c, rec, _, _ = parts
    rec.fail = OSError("マイクが見つかりません")
    with qtbot.waitSignal(c.notify):
        c.toggle()
    assert c.current == State.IDLE
    assert c.error and c.bubble == "マイクが見つかりません"


def test_cancel_discards(parts) -> None:
    c, rec, asr, _ = parts
    c.toggle()
    c.cancel()
    assert c.current == State.IDLE
    assert rec.cancelled == 1 and asr.audio == []


def test_history_newest_first_dedup_and_limited(qtbot: QtBot, parts) -> None:
    c, *_ = parts
    for i in [*range(12), 5]:
        c.post_inject_result(Result(f"文{i}", Status.INJECTED))
    qtbot.waitUntil(lambda: list(c.history)[:1] == ["文5"])
    assert len(c.history) == 10
    assert list(c.history).count("文5") == 1


def test_modifier_timeout_kept_in_history(qtbot: QtBot, parts) -> None:
    c, *_ = parts
    with qtbot.waitSignal(c.notify):
        c.post_inject_result(Result("残す", Status.MODIFIER_TIMEOUT))
    assert list(c.history) == ["残す"]
    assert c.error


def test_reinject_skips_postprocess(qtbot: QtBot, parts) -> None:
    c, _, _, inj = parts
    c.reinject("履歴の文")
    assert c.current == State.INJECTING
    qtbot.waitUntil(lambda: inj.texts == [("履歴の文", True)])


def test_reinject_activates_target_first(qtbot: QtBot, parts) -> None:
    c, _, _, inj = parts
    activated: list[int] = []
    c.activate_window = activated.append
    c.reinject("履歴の文", target=1234)
    qtbot.waitUntil(lambda: inj.targets == [1234])
    assert activated == [1234]


def test_stop_failure_returns_to_idle(qtbot: QtBot, parts) -> None:
    c, rec, asr, _ = parts
    c.toggle()
    rec.stop_fail = OSError("デバイスが外れました")
    with qtbot.waitSignal(c.notify):
        c.toggle()
    assert c.current == State.IDLE
    assert asr.audio == []


def test_level_polled_while_recording(qtbot: QtBot, parts) -> None:
    c, rec, _, _ = parts
    c.toggle()
    rec.level = 0.5
    qtbot.waitUntil(lambda: c.level == 0.5)
    c.toggle()
    assert c.level == 0.0
