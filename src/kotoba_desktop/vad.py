"""Silero VAD で発話区間を切り出し、認識に渡すかたまりに分ける。

kotoba-whisper v2.0 は 20 秒を超える音声を 1 度に渡すと、末尾の文を落とすことがある
（Phase 0 で確認）。そのため発話区間を max_chunk_s 以内のかたまりにまとめ、かたまりごとに認識する。
"""

import numpy as np

SAMPLE_RATE = 16000


def speech_spans(audio: np.ndarray, max_span_s: float = 15.0) -> list[tuple[int, int]]:
    """発話区間を (開始, 終了) のサンプル位置で返す。

    途切れなく話し続けても 1 区間が max_span_s を超えないよう、Silero VAD 側で
    静かな箇所で分割させる。
    """
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    options = VadOptions(
        min_silence_duration_ms=300, speech_pad_ms=200, max_speech_duration_s=max_span_s
    )
    return [(t["start"], t["end"]) for t in get_speech_timestamps(audio, options)]


def group_spans(spans: list[tuple[int, int]], max_samples: int) -> list[tuple[int, int]]:
    """隣り合う発話区間を、全体の長さが max_samples を超えない範囲でまとめる。

    1 つの区間だけで max_samples を超える場合は、その区間をそのまま 1 つのかたまりにする。
    """
    chunks: list[tuple[int, int]] = []
    for start, end in spans:
        if chunks and end - chunks[-1][0] <= max_samples:
            chunks[-1] = (chunks[-1][0], end)
        else:
            chunks.append((start, end))
    return chunks


def speech_chunks(
    audio: np.ndarray, *, min_speech_ms: int = 300, max_chunk_s: float = 15.0
) -> list[np.ndarray]:
    """認識に渡す音声のかたまりを返す。発話の合計が min_speech_ms 未満なら空。"""
    spans = speech_spans(audio, max_chunk_s)
    total = sum(end - start for start, end in spans)
    if total < SAMPLE_RATE * min_speech_ms / 1000:
        return []
    return [audio[s:e] for s, e in group_spans(spans, int(SAMPLE_RATE * max_chunk_s))]
