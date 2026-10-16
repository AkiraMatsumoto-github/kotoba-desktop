# kotoba-desktop

Windows に常駐する日本語の音声入力アプリです。ショートカットキーで録音を開始し、もう一度押して終了すると、話した内容を [kotoba-whisper](https://huggingface.co/kotoba-tech/kotoba-whisper-v2.0-faster) で GPU 認識し、フォーカス中のテキスト欄へまとめて入力します。

WSL のターミナルや Cursor へも文字の順序を崩さずに入力できるよう、1 文字ずつのキー送信ではなく、クリップボード経由の 1 回の貼り付けで入力します（元のクリップボードの内容は入力後に戻します）。

> 開発中です（Phase 0 の技術検証と MVP の実装が済み、人の手による検証待ち）。

設計の詳細は [設計書](docs/design.md)、進捗は [開発計画](docs/plan.md) を参照してください。

## 動作環境

- Windows 11
- NVIDIA GPU（CUDA 12.8 以降に対応したドライバ）
- [uv](https://docs.astral.sh/uv/)

## セットアップ

```powershell
uv sync
uv run hf download kotoba-tech/kotoba-whisper-v2.0-faster
```

## 使い方

```powershell
uv run kotoba-desktop
```

タスクトレイにアイコンが出て、モデルを読み込み終わると使えます（10 秒ほど）。

- **Ctrl+H** で録音を開始し、もう一度 **Ctrl+H** で終了すると、認識した文がカーソル位置に入力されます。Enter は送りません。
- 録音を始めるとウィジェットが出ます。「聞き取り中…」に変わってから話し始めてください（マイクによっては、開いてから音が届くまで 0.5 秒ほどかかります）。
- ウィジェットのマイクボタンでも開始・終了できます。クリックしても入力先のフォーカスは移りません。閉じるボタンは録音を破棄します。
- 入力に失敗したときは、トレイのメニューの「履歴」から入力し直せます。

Ctrl+H はどのアプリにも届かなくなるため、VS Code / Cursor の置換などが使えなくなります。困る場合は設定でキーを変えてください。

### 設定

設定ファイルは `%APPDATA%\kotoba-desktop\config.toml` です（初回起動時に作られます）。トレイの「設定を開く」で開き、保存してから「設定を再読み込み」で反映します。主な項目:

| 項目 | 内容 |
| --- | --- |
| `[hotkey] key` / `modifiers` | ショートカットキー（既定は Ctrl+H） |
| `[audio] keep_open` | `true` でマイクを開いたままにし、押す直前 0.3 秒も録る。話し始めが欠けるとき用（タスクバーのマイク使用中表示が出続けます） |
| `[inject.profile]` | アプリ別の貼り付けキー（Windows Terminal は Shift+Insert） |
| `[text] punctuation` | `keep`（モデルの出力のまま）/ `strip`（「、。」を除く） |
| `[text.replace]` | 置換辞書（例: `"クロードコード" = "Claude Code"`） |

ログは `%APPDATA%\kotoba-desktop\kotoba-desktop.log` に出ます。認識した文字列そのものはログにも残しません。

### ログオン時に自動起動する

```powershell
uv tool install --editable .
powershell -ExecutionPolicy Bypass -File tools\install_startup.ps1
```

`%USERPROFILE%\.local\bin\kotoba-desktop.exe`（コンソール窓なし）が作られ、スタートアップフォルダにショートカットが置かれます。editable なので、コードを直したら再起動するだけで反映されます。解除は `install_startup.ps1 -Remove` です。

## 開発

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

`.venv` は Windows 用に作られます。WSL から作業する場合も、`uv sync` や `uv run` は Windows 側の `uv.exe` で実行してください。

### Phase 0 の検証スクリプト

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
  app.py          部品の組み立て、設定の再読み込み
  controller.py   状態遷移（待機 → 録音中 → 認識中 → 入力中）
  hotkey.py       ショートカットキーの登録と待ち受け
  audio.py        録音と 16 kHz への変換
  vad.py          発話区間の切り出し（Silero VAD）
  asr.py          音声認識（faster-whisper）
  recognizer.py   認識ワーカーのスレッド
  textproc.py     認識結果の後処理
  config.py       設定ファイルの読み込みと検証
  keys.py         キーの組み合わせの解析
  state.py        ウィジェットの位置などの保存
  win32/          Win32 API のラッパー（SendInput、クリップボード、ウィンドウ、IME）
  inject/         テキスト欄への入力（プロファイル、貼り付け、打鍵、入力スレッド）
  ui/             ウィジェット（Qt Quick）とトレイアイコン
```
