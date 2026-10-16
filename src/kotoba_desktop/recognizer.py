"""認識ワーカー。GPU を使うのはこのスレッドだけで、モデルは起動時に読み込んで保持する。"""

import logging
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from kotoba_desktop.asr import Engine, recognize
from kotoba_desktop.config import AudioConfig
from kotoba_desktop.vad import speech_chunks

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Recognition:
    text: str  # 発話が無ければ空
    seconds: float  # VAD から認識までにかかった時間
    error: str = ""


class Recognizer:
    def __init__(
        self,
        make_engine: Callable[[], Engine],
        get_audio_config: Callable[[], AudioConfig],
        on_loaded: Callable[[str], None],  # 引数はエラーメッセージ（成功なら空）
        on_result: Callable[[Recognition], None],
    ) -> None:
        self._make_engine = make_engine
        self._get_audio_config = get_audio_config
        self._on_loaded = on_loaded
        self._on_result = on_result
        self._queue: queue.Queue[np.ndarray | None] = queue.Queue()
        self._thread = threading.Thread(target=self._run, name="recognizer", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._queue.put(None)

    def submit(self, audio: np.ndarray) -> None:
        self._queue.put(audio)

    def _run(self) -> None:
        try:
            t = time.perf_counter()
            engine = self._make_engine()
            warmup = getattr(engine, "warmup", None)
            if warmup:
                warmup()
            log.info("モデルを読み込みました（%.1f 秒）", time.perf_counter() - t)
        except Exception as e:
            log.exception("モデルの読み込みに失敗")
            self._on_loaded(f"モデルを読み込めません: {e}")
            return
        self._on_loaded("")

        while (audio := self._queue.get()) is not None:
            t = time.perf_counter()
            try:
                cfg = self._get_audio_config()
                chunks = speech_chunks(
                    audio, min_speech_ms=cfg.min_speech_ms, max_chunk_s=cfg.max_chunk_s
                )
                text = recognize(engine, chunks) if chunks else ""
                result = Recognition(text, time.perf_counter() - t)
            except Exception as e:
                log.exception("認識に失敗")
                result = Recognition("", time.perf_counter() - t, f"認識に失敗しました: {e}")
            log.info(
                "認識 %.2f 秒（音声 %.1f 秒、%d 文字）",
                result.seconds,
                len(audio) / 16000,
                len(result.text),
            )
            self._on_result(result)
