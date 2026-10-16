import numpy as np

from kotoba_desktop.vad import group_spans, speech_chunks


def test_group_spans_within_limit() -> None:
    spans = [(0, 10), (12, 20), (25, 40), (41, 45)]
    assert group_spans(spans, 20) == [(0, 20), (25, 45)]


def test_group_spans_long_single_span_kept() -> None:
    assert group_spans([(0, 100), (101, 105)], 20) == [(0, 100), (101, 105)]


def test_group_spans_empty() -> None:
    assert group_spans([], 20) == []


def test_silence_yields_no_chunks() -> None:
    assert speech_chunks(np.zeros(16000 * 2, dtype=np.float32)) == []
