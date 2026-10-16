"""P0-02: 検証用の音声を作る。

Windows の音声合成（System.Speech、日本語ボイス）で文面が分かっている発話を合成し、
無音と雑音だけの音声も合わせて tools/poc/samples/ に 16 kHz モノラルの WAV で書き出す。

    uv run python tools/poc/make_samples.py
"""

import subprocess
import wave
from pathlib import Path

import numpy as np

SAMPLES = Path(__file__).parent / "samples"
RATE = 16000

# 3 / 10 / 25 秒前後になる文面と、英語混じりの文面
SPEECH = {
    "speech_03s": "今日はいい天気ですね。",
    "speech_10s": (
        "音声入力アプリを使って、話した内容をそのままテキスト欄へ入力します。"
        "認識結果は一度にまとめて貼り付けます。"
    ),
    "speech_25s": (
        "このアプリは Windows に常駐し、ショートカットキーを押している間に話した日本語を、"
        "GPU で認識してフォーカスされている入力欄へ貼り付けます。"
        "ターミナルでは一文字ずつ送ると順番が入れ替わることがあるため、"
        "クリップボードを使って一回で渡します。"
        "貼り付けた後は、元のクリップボードの内容を戻します。"
    ),
    "speech_mixed": "Claude Code で WSL のターミナルに Python のコードを入力します。",
}

VOICE = "Microsoft Haruka Desktop"


def synthesize(text: str, path: Path) -> None:
    """System.Speech で text を 16 kHz 16 bit モノラルの WAV に合成する。"""
    script = f"""
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SelectVoice('{VOICE}')
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(
    {RATE}, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,
    [System.Speech.AudioFormat.AudioChannel]::Mono)
$s.SetOutputToWaveFile('{path}', $fmt)
$s.Speak([Console]::In.ReadToEnd())
$s.Dispose()
"""
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        input=text,
        text=True,
        encoding="utf-8",
        check=True,
    )


def write_wav(path: Path, audio: np.ndarray) -> None:
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())


def main() -> None:
    SAMPLES.mkdir(parents=True, exist_ok=True)
    for name, text in SPEECH.items():
        wav = SAMPLES / f"{name}.wav"
        synthesize(text, wav)
        (SAMPLES / f"{name}.txt").write_text(text, encoding="utf-8")
        with wave.open(str(wav)) as w:
            print(f"{wav.name}: {w.getnframes() / w.getframerate():.1f} 秒")

    rng = np.random.default_rng(0)
    write_wav(SAMPLES / "silence.wav", np.zeros(RATE * 3))
    write_wav(SAMPLES / "noise_white.wav", rng.normal(0, 0.02, RATE * 3))
    # ファンの音に近い低域寄りの雑音（白色雑音を累積してから高域を落とす）
    brown = np.cumsum(rng.normal(0, 1, RATE * 3))
    brown -= np.convolve(brown, np.ones(400) / 400, mode="same")
    write_wav(SAMPLES / "noise_brown.wav", brown / np.abs(brown).max() * 0.1)
    print("silence.wav / noise_white.wav / noise_brown.wav: 3.0 秒")


if __name__ == "__main__":
    main()
