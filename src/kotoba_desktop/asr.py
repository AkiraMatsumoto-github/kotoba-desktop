"""音声認識エンジンのインターフェースと faster-whisper 実装。"""

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

SAMPLE_RATE = 16000


class Engine(Protocol):
    """16 kHz モノラル float32 の音声を受け取り、認識した文字列を返す。"""

    def transcribe(self, audio: np.ndarray) -> str: ...


def register_cuda_dlls() -> None:
    """pip で入れた NVIDIA ライブラリ（cuBLAS など）の DLL を検索パスに加える。

    ctranslate2 の wheel には cuBLAS が含まれないため、nvidia-cublas-cu12 の bin を登録する。
    """
    if sys.platform != "win32":
        return
    # PyInstaller で固めたアプリでは _internal（sys._MEIPASS）の下に nvidia/*/bin を置く
    bundle = getattr(sys, "_MEIPASS", None)
    for site in map(Path, dict.fromkeys([bundle, *sys.path] if bundle else sys.path)):
        nvidia = site / "nvidia"
        if not nvidia.is_dir():
            continue
        for bin_dir in nvidia.glob("*/bin"):
            os.add_dll_directory(str(bin_dir))
            # ctranslate2 は LoadLibrary を素の名前で呼ぶため PATH にも入れる
            os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"


@dataclass(frozen=True)
class Segment:
    text: str
    no_speech_prob: float
    avg_logprob: float


class FasterWhisperEngine:
    """faster-whisper（CTranslate2）で Whisper 系のモデル（既定は large-v3-turbo）を動かす。"""

    def __init__(
        self,
        model: str = "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
        *,
        device: str = "cuda",
        compute_type: str = "float16",
        beam_size: int = 1,
        hotwords: str = "",
        no_speech_threshold: float = 0.6,
        local_files_only: bool = False,
    ) -> None:
        register_cuda_dlls()
        from faster_whisper import WhisperModel

        self._model = WhisperModel(
            model,
            device=device,
            compute_type=compute_type,
            local_files_only=local_files_only,
        )
        self._beam_size = beam_size
        self._hotwords = hotwords or None
        self._no_speech_threshold = no_speech_threshold

    def warmup(self) -> None:
        """初回推論の CUDA 初期化を起動時に済ませる（無音 1 秒を認識する）。"""
        self.segments(np.zeros(SAMPLE_RATE, dtype=np.float32))

    def segments(self, audio: np.ndarray) -> list[Segment]:
        """区間ごとの認識結果を返す（no_speech_prob による除外はしない）。"""
        result, _ = self._model.transcribe(
            audio,
            language="ja",
            task="transcribe",
            beam_size=self._beam_size,
            condition_on_previous_text=False,
            without_timestamps=True,
            vad_filter=False,
            hotwords=self._hotwords,
        )
        return [Segment(s.text, s.no_speech_prob, s.avg_logprob) for s in result]

    def transcribe(self, audio: np.ndarray) -> str:
        threshold = self._no_speech_threshold
        kept = [s.text for s in self.segments(audio) if s.no_speech_prob < threshold]
        return "".join(kept).strip()


def recognize(engine: Engine, chunks: list[np.ndarray]) -> str:
    """VAD で分けたかたまりを順に認識してつなげる。"""
    return "".join(engine.transcribe(c) for c in chunks)
