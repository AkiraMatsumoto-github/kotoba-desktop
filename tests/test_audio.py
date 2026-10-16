"""Recorder のバッファ処理。マイクは開かず、PortAudio のコールバックを直接呼ぶ。"""

import numpy as np
import pytest

from kotoba_desktop.audio import Recorder, resample


class FakeStream:
    def __init__(self) -> None:
        self.closed = False

    def stop(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


def block(value: float, frames: int = 480) -> np.ndarray:
    return np.full((frames, 1), value, dtype=np.float32)


def opened(keep_open: bool, ready: list[int] | None = None) -> Recorder:
    """マイクを開いた状態の Recorder（48 kHz）。"""
    r = Recorder(
        keep_open=keep_open, on_ready=(lambda: ready.append(1)) if ready is not None else None
    )
    r._stream = FakeStream()  # ty: ignore[invalid-assignment]
    r._rate = 48000
    return r


def test_records_between_start_and_stop() -> None:
    ready: list[int] = []
    r = opened(keep_open=False, ready=ready)
    r.start()
    assert ready == []  # 最初の音が届くまでは準備中
    for _ in range(100):  # 1 秒分
        r._callback(block(0.1), 480, None, None)
    assert ready == [1]  # 最初のブロックで 1 回だけ知らせる
    audio = r.stop()
    assert audio.dtype == np.float32
    assert abs(len(audio) - 16000) <= 16
    assert r._stream is None  # keep_open=False なら閉じる


def test_preroll_keeps_last_300ms() -> None:
    ready: list[int] = []
    r = opened(keep_open=True, ready=ready)
    for i in range(100):  # 押す前の 1 秒。値でブロックの順番が分かるようにする
        r._callback(block(i / 100), 480, None, None)
    r.start()
    assert ready == [1]  # 直前の音があるので、すぐに話し始めてよい
    r._callback(block(1.0), 480, None, None)
    audio = r._blocks
    total = sum(len(b) for b in audio)
    # 直前 0.3 秒（14400 サンプル）以上、1 ブロック分の余裕まで
    assert 14400 <= total - 480 < 14400 + 480
    assert audio[-1][0] == 1.0 and audio[0][0] > 0.6  # 古い音は捨てている
    r.stop()
    assert r._stream is not None  # keep_open=True なら開いたまま


def test_cancel_discards_without_converting() -> None:
    r = opened(keep_open=False)
    r.start()
    r._callback(block(0.1), 480, None, None)
    r.cancel()
    assert not r.recording
    assert r._blocks == []
    assert r._stream is None


def test_start_failure_rolls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    r = Recorder()

    def fail() -> None:
        raise OSError("マイクが見つかりません")

    monkeypatch.setattr(r, "open", fail)
    with pytest.raises(OSError):
        r.start()
    assert not r.recording


def test_resample_to_16k() -> None:
    audio = np.sin(np.linspace(0, 100, 48000)).astype(np.float32)
    out = resample(audio, 48000)
    assert out.dtype == np.float32
    assert len(out) == 16000
