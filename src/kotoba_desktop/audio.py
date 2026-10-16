"""マイクから録音し、16 kHz モノラルに変換する。

WASAPI 共有モードでデバイス本来のレートのまま取り、録音終了後に soxr でまとめて変換する。
既定ではマイクを録音中だけ開く（開いたままだとタスクバーのマイク使用中表示が消えない）。
"""

import threading
from collections import deque
from collections.abc import Callable

import numpy as np

SAMPLE_RATE = 16000


class AudioError(OSError):
    pass


def _wasapi_index() -> int:
    import sounddevice as sd

    for i, api in enumerate(sd.query_hostapis()):
        if api["name"] == "Windows WASAPI":
            return i
    raise AudioError("WASAPI が見つかりません")


def input_devices() -> list[str]:
    """WASAPI の入力デバイス名の一覧（トレイのマイク選択用）。"""
    import sounddevice as sd

    api = _wasapi_index()
    return [
        d["name"] for d in sd.query_devices() if d["hostapi"] == api and d["max_input_channels"] > 0
    ]


def find_device(name: str) -> dict:
    """name を含む WASAPI 入力デバイス。空なら WASAPI の既定の入力デバイス。"""
    import sounddevice as sd

    api = _wasapi_index()
    if not name:
        index = sd.query_hostapis(api)["default_input_device"]
        if index < 0:
            raise AudioError("マイクが見つかりません")
        return sd.query_devices(index)
    inputs = [d for d in sd.query_devices() if d["hostapi"] == api and d["max_input_channels"] > 0]
    # トレイから選んだときは正確な名前なので完全一致を優先し、無ければ部分一致
    for d in inputs:
        if d["name"] == name:
            return d
    for d in inputs:
        if name in d["name"]:
            return d
    raise AudioError(f"マイク「{name}」が見つかりません")


class Recorder:
    """start() から stop() までの音声を 16 kHz モノラル float32 で返す。

    keep_open=False（既定）: 録音中だけマイクを開く。デバイスによっては開いてから最初の音が届くまで
    0.5 秒近くかかる（Phase 0 で計測）ので、届いたら on_ready を呼んで話し始めてよいことを知らせる。
    keep_open=True: マイクを開いたままにし、start() の直前 PREROLL_S 秒も録音に含める。
    """

    PREROLL_S = 0.3

    def __init__(
        self,
        device: str = "",
        *,
        keep_open: bool = False,
        on_ready: Callable[[], None] | None = None,
    ) -> None:
        self.device = device
        self.keep_open = keep_open
        self.level = 0.0  # 直近のブロックの音量（0〜1）。ウィジェットの表示用
        self._on_ready = on_ready
        self._stream = None
        self._rate = 0
        self._recording = False
        self._notified = False
        self._blocks: list[np.ndarray] = []
        self._preroll: deque[np.ndarray] = deque()
        self._preroll_len = 0
        self._lock = threading.Lock()

    @property
    def recording(self) -> bool:
        return self._recording

    def open(self) -> None:
        """マイクを開く（keep_open のときは起動時に呼ぶ）。"""
        import sounddevice as sd

        if self._stream is not None:
            return
        info = find_device(self.device)
        self._rate = int(info["default_samplerate"])
        try:
            stream = sd.InputStream(
                device=info["index"],
                samplerate=self._rate,
                channels=1,
                dtype="float32",
                callback=self._callback,
            )
            stream.start()
        except sd.PortAudioError as e:
            raise AudioError(f"マイクを開けません: {e}") from e
        self._stream = stream

    def close(self) -> None:
        stream, self._stream = self._stream, None
        if stream is not None:
            stream.stop()
            stream.close()
        with self._lock:
            self._preroll.clear()
            self._preroll_len = 0

    def start(self) -> None:
        if self._recording:
            return
        with self._lock:
            self._blocks = list(self._preroll)
            self._preroll.clear()
            self._preroll_len = 0
            self._notified = bool(self._blocks)
            self._recording = True
        if self._stream is None:
            try:
                self.open()
            except Exception:
                self._recording = False
                raise
        if self._notified and self._on_ready:
            self._on_ready()

    def _callback(self, indata: np.ndarray, frames: int, time: object, status: object) -> None:
        # PortAudio のスレッドから呼ばれる。バッファに積むだけにする
        block = indata[:, 0].copy()
        notify = False
        with self._lock:
            if self._recording:
                self._blocks.append(block)
                notify, self._notified = not self._notified, True
            else:
                self._preroll.append(block)
                self._preroll_len += len(block)
                while self._preroll_len - len(self._preroll[0]) >= self.PREROLL_S * self._rate:
                    self._preroll_len -= len(self._preroll.popleft())
        if self._recording:
            self.level = min(1.0, float(np.sqrt(np.mean(block**2))) * 10)
        if notify and self._on_ready:
            self._on_ready()

    def stop(self) -> np.ndarray:
        """録音を止め、16 kHz に変換した音声を返す。"""
        with self._lock:
            self._recording = False
            blocks, self._blocks = self._blocks, []
        if not self.keep_open:
            self.close()
        self.level = 0.0
        if not blocks:
            return np.zeros(0, dtype=np.float32)
        return resample(np.concatenate(blocks), self._rate)

    def cancel(self) -> None:
        """録音を捨てて止める（変換はしない）。"""
        with self._lock:
            self._recording = False
            self._blocks = []
        if not self.keep_open:
            self.close()
        self.level = 0.0


def resample(audio: np.ndarray, rate: int) -> np.ndarray:
    if rate == SAMPLE_RATE:
        return audio.astype(np.float32, copy=False)
    import soxr

    return soxr.resample(audio, rate, SAMPLE_RATE).astype(np.float32, copy=False)
