# kotoba-input

Windows に常駐する日本語の音声入力アプリです。ショートカットキーで録音を開始し、もう一度押して終了すると、話した内容を [kotoba-whisper](https://huggingface.co/kotoba-tech/kotoba-whisper-v2.0-faster) で GPU 認識し、フォーカス中のテキスト欄へまとめて入力します。

WSL のターミナルや Cursor へも文字の順序を崩さずに入力できるよう、1 文字ずつのキー送信ではなく、クリップボード経由の 1 回の貼り付けで入力します（元のクリップボードの内容は入力後に戻します）。

> 開発中です（Phase 0: 技術検証）。まだ動作しません。

設計の詳細は [設計書](docs/design.md) を参照してください。

## 動作環境

- Windows 11
- NVIDIA GPU（CUDA 12.8 以降に対応したドライバ）
- [uv](https://docs.astral.sh/uv/)

## セットアップ

```powershell
uv sync
uv run hf download kotoba-tech/kotoba-whisper-v2.0-faster
```

## 開発

```powershell
uv run ruff check
uv run ruff format
uv run ty check
uv run pytest
```

`.venv` は Windows 用に作られます。WSL から作業する場合も、`uv sync` や `uv run` は Windows 側の `uv.exe` で実行してください。

## 構成

```text
src/kotoba_input/
  __main__.py     エントリポイント
  controller.py   状態遷移（待機 → 録音中 → 認識中 → 入力中）
  hotkey.py       ショートカットキーの登録と待ち受け
  audio.py        録音と 16 kHz への変換
  asr.py          音声認識（faster-whisper）
  textproc.py     認識結果の後処理
  config.py       設定ファイルの読み込みと検証
  win32/          Win32 API のラッパー
  inject/         テキスト欄への入力
  ui/             ウィジェットとトレイアイコン
```
