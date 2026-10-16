# 開発者向けガイド

kotoba-desktop の開発に参加する人向けの情報です。使い方は [README](../README.md) を参照してください。設計の詳細は [設計書](design.md)、進捗は [開発計画](plan.md) にあります。

## 開発環境

```powershell
uv sync
uv run hf download kotoba-tech/kotoba-whisper-v2.0-faster
uv run kotoba-desktop
```

`.venv` は Windows 用に作られます。WSL から作業する場合も、`uv sync` や `uv run` は Windows 側の `uv.exe` で実行してください（WSL の uv で同じ `.venv` を触らない）。

環境変数 `KOTOBA_DEBUG=1` を付けて起動すると、ログがターミナルにも出ます。

## 検査とテスト

```powershell
uv run ruff check
uv run ruff format
uv run ty check
uv run pytest
```

実際のクリップボードやキー入力を使う結合テストは、手元のクリップボードを一時的に書き換えるため、明示したときだけ動きます。

```powershell
$env:KOTOBA_INTEGRATION = "1"; uv run pytest
```

GitHub Actions（`.github/workflows/ci.yml`）では、GPU なしで lint・型チェック・単体テストを回します。

## Phase 0 の検証スクリプト

| スクリプト | 内容 |
| --- | --- |
| `tools/poc/make_samples.py` | 音声合成で検証用の発話・無音・雑音を作る |
| `tools/poc/asr_bench.py` | GPU 推論・遅延・VRAM・句読点・無音時の出力を計測する |
| `tools/inject_check.py` | 既知の文字列を入力し、受信側の記録と照合する（使い方は `--help`） |
| `tools/poc/recv.py` | WSL のターミナル側の受信スクリプト（WSL の `python3` で実行） |
| `tools/poc/receiver.html` | Chrome 用の受信ページ |
| `tools/poc/focus_watch.py` | 前面ウィンドウの変化を記録する（ウィジェットがフォーカスを奪わないかの確認） |

## 構成

```text
src/kotoba_desktop/
  __main__.py     エントリポイント（二重起動の防止、ログ）
  app.py          部品の組み立て、設定の反映
  controller.py   状態遷移（待機 → 録音中 → 認識中 → 入力中）
  hotkey.py       ショートカットキーの登録と待ち受け
  audio.py        録音と 16 kHz への変換
  vad.py          発話区間の切り出し（Silero VAD）
  asr.py          音声認識（faster-whisper）
  recognizer.py   認識ワーカーのスレッド
  textproc.py     認識結果の後処理
  config.py       設定ファイルの読み書きと検証
  keys.py         キーの組み合わせの解析
  state.py        ウィジェットの位置などの保存
  win32/          Win32 API のラッパー（SendInput、クリップボード、ウィンドウ、IME）
  inject/         テキスト欄への入力（プロファイル、貼り付け、打鍵、入力スレッド）
  ui/             ウィジェット（Qt Quick）、トレイアイコン、設定画面
```
