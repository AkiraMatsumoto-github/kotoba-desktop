"""P0-03〜P0-07: GPU 推論・遅延・VRAM・句読点・無音時の出力を確かめる。

遅延は VAD での切り出しから認識まで（本番と同じ経路）を測る。

先に make_samples.py で検証用の音声を作っておく。

    uv run python tools/poc/asr_bench.py [--runs 10] [--beam-size 1]
"""

import argparse
import json
import statistics
import subprocess
import threading
import time
import wave
from pathlib import Path

import numpy as np

from kotoba_desktop.asr import FasterWhisperEngine, recognize
from kotoba_desktop.vad import speech_chunks

POC = Path(__file__).parent
SAMPLES = POC / "samples"
OUT = POC / "out"


def load_wav(path: Path) -> np.ndarray:
    with wave.open(str(path)) as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    return pcm.astype(np.float32) / 32768


def gpu_used_mib() -> int:
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return int(out.split()[0])


class PeakMonitor:
    """GPU メモリ使用量の最大値を裏で記録する。"""

    def __init__(self) -> None:
        self.peak = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.is_set():
            self.peak = max(self.peak, gpu_used_mib())
            time.sleep(0.05)

    def __enter__(self) -> PeakMonitor:
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        self._thread.join()


def normalize(text: str) -> str:
    """CER の比較用に句読点と空白を除く。"""
    return "".join(c for c in text if c not in "、。，．,. 　!?！？")  # noqa: RUF001


def cer(ref: str, hyp: str) -> float:
    ref, hyp = normalize(ref), normalize(hyp)
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i]
        for j, h in enumerate(hyp, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h)))
        prev = cur
    return prev[-1] / max(len(ref), 1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--beam-size", type=int, default=1)
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True)
    report: dict[str, object] = {"beam_size": args.beam_size}

    base = gpu_used_mib()
    t = time.perf_counter()
    engine = FasterWhisperEngine(beam_size=args.beam_size, local_files_only=True)
    load_s = time.perf_counter() - t
    t = time.perf_counter()
    engine.warmup()
    warmup_s = time.perf_counter() - t
    resident = gpu_used_mib() - base
    print(f"[P0-03] 読み込み {load_s:.1f} 秒、ウォームアップ {warmup_s:.2f} 秒")
    print(f"[P0-05] 常駐中の VRAM 増加 {resident} MiB（読み込み前 {base} MiB）")
    report |= {"load_s": load_s, "warmup_s": warmup_s, "vram_base_mib": base}
    report["vram_resident_mib"] = resident

    speech = sorted(SAMPLES.glob("speech_*.wav"))
    results = {}
    with PeakMonitor() as peak:
        for wav in speech:
            audio = load_wav(wav)
            ref = wav.with_suffix(".txt").read_text(encoding="utf-8")
            times, text = [], ""
            for _ in range(args.runs):
                t = time.perf_counter()
                text = recognize(engine, speech_chunks(audio))
                times.append(time.perf_counter() - t)
            med = statistics.median(times)
            results[wav.stem] = {
                "audio_s": len(audio) / 16000,
                "median_s": med,
                "max_s": max(times),
                "text": text,
                "reference": ref,
                "cer": cer(ref, text),
                "has_punctuation": any(c in text for c in "、。"),
            }
            r = results[wav.stem]
            print(
                f"[P0-04] {wav.stem}（{r['audio_s']:.1f} 秒）: 中央値 {med:.3f} 秒、"
                f"最大 {r['max_s']:.3f} 秒、CER {r['cer']:.1%}"
            )
            print(f"        正解: {ref}\n        認識: {text}")
    report["speech"] = results
    report["vram_peak_mib"] = peak.peak - base
    print(f"[P0-05] 認識中の VRAM 増加（最大） {peak.peak - base} MiB")

    punct = {k: v["has_punctuation"] for k, v in results.items()}
    print(f"[P0-06] 句読点が付いたか: {punct}")

    silent = {}
    for name in ("silence", "noise_white", "noise_brown"):
        audio = load_wav(SAMPLES / f"{name}.wav")
        segs = engine.segments(audio)
        silent[name] = {
            "segments": [s.__dict__ for s in segs],
            "transcribe": engine.transcribe(audio),
            "pipeline": recognize(engine, speech_chunks(audio)),
        }
        print(
            f"[P0-07] {name}: VAD なし={silent[name]['transcribe']!r}、"
            f"VAD あり={silent[name]['pipeline']!r}"
        )
        for s in segs:
            print(
                f"        {s.text!r} no_speech={s.no_speech_prob:.2f} logprob={s.avg_logprob:.2f}"
            )
    report["silent"] = silent

    out = OUT / f"asr_bench_beam{args.beam_size}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"結果: {out}")


if __name__ == "__main__":
    main()
