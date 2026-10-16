"""部品を組み立て、設定の再読み込みや終了を受け持つ。"""

import logging
import os
import subprocess
from pathlib import Path

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication

from kotoba_desktop import config
from kotoba_desktop.asr import FasterWhisperEngine
from kotoba_desktop.audio import AudioError, Recorder, input_devices
from kotoba_desktop.config import Config, ConfigError
from kotoba_desktop.controller import Controller
from kotoba_desktop.hotkey import HotkeyError, HotkeyListener
from kotoba_desktop.inject.injector import Injector
from kotoba_desktop.recognizer import Recognizer
from kotoba_desktop.state import State as AppState
from kotoba_desktop.ui.tray import Tray
from kotoba_desktop.ui.widget import Widget
from kotoba_desktop.win32 import window

log = logging.getLogger(__name__)

TITLE = "kotoba-desktop"


def model_cached(model: str) -> bool:
    """モデルが手元にあるか（ローカルのディレクトリか、Hugging Face のキャッシュにあるか）。"""
    if Path(model).is_dir():
        return True
    from huggingface_hub import try_to_load_from_cache

    return isinstance(try_to_load_from_cache(model, "model.bin"), str)


class App(QObject):
    def __init__(self, qapp: QApplication) -> None:
        super().__init__()
        self._qapp = qapp
        self.config_path = config.config_path()
        startup_error = ""
        try:
            self.config = config.load(self.config_path)
        except ConfigError as e:
            startup_error = f"{e}\n既定の設定で起動しました"
            self.config = Config()

        self.app_state = AppState()
        self.recorder = Recorder(
            self.config.audio.device,
            keep_open=self.config.audio.keep_open,
            on_ready=lambda: self.controller.post_mic_ready(),
        )
        self.injector = Injector(
            lambda: self.config, lambda r: self.controller.post_inject_result(r)
        )
        self.recognizer = Recognizer(
            self._make_engine,
            lambda: self.config.audio,
            on_loaded=lambda e: self.controller.post_loaded(e),
            on_result=lambda r: self.controller.post_recognized(r),
        )
        self.controller = Controller(
            self.recorder, self.recognizer, self.injector, self.config.hotkey.chord.display
        )
        self.controller.activate_window = window.activate
        self.widget = Widget(self.controller, self.app_state, self.config.widget.always_show)

        # トレイの履歴から再入力するときの入力先として、直近の前面ウィンドウを覚えておく
        # （トレイを開くと前面がタスクバーに移るため、開いた時点では分からない）
        self._last_target: int | None = None
        self._target_timer = QTimer(self, interval=300)
        self._target_timer.timeout.connect(self._track_target)
        self._target_timer.start()

        self.tray = Tray(
            self.controller,
            input_devices,
            lambda: self.config.audio.device,
            self.config.widget.always_show,
            lambda: self._last_target,
        )

        self.widget.settingsRequested.connect(self.open_settings)
        self.widget.helpRequested.connect(self.show_help)
        self.tray.openSettingsRequested.connect(self.open_settings)
        self.tray.reloadRequested.connect(self.reload)
        self.tray.quitRequested.connect(self.quit)
        self.tray.showWidgetRequested.connect(self.widget.show)
        self.tray.alwaysShowToggled.connect(self.set_always_show)
        self.tray.deviceSelected.connect(self.set_device)

        if startup_error:
            self.tray.show_message(TITLE, startup_error)
        self.hotkey: HotkeyListener | None = None
        self._register_hotkey(self.config)
        if self.config.audio.keep_open:
            self._open_mic()
        self.injector.start()
        self.recognizer.start()

    def _track_target(self) -> None:
        hwnd = window.user32.GetForegroundWindow()
        if not hwnd or hwnd == self._last_target:
            return
        info = window.window_info(hwnd)
        if window.is_input_target(info, os.getpid()):
            self._last_target = hwnd

    # --- 起動 ---

    def _make_engine(self) -> FasterWhisperEngine:
        """認識ワーカーのスレッドで呼ばれる。"""
        cfg = self.config.asr
        cached = model_cached(cfg.model)
        if not cached:
            self.controller.notify.emit(
                TITLE, "モデルをダウンロードしています（初回のみ、約 1.5 GB）"
            )
        return FasterWhisperEngine(
            cfg.model,
            device=cfg.device,
            compute_type=cfg.compute_type,
            beam_size=cfg.beam_size,
            hotwords=cfg.hotwords,
            no_speech_threshold=cfg.no_speech_threshold,
            local_files_only=cached,  # 取得済みならネットワークに触れない
        )

    def _register_hotkey(self, cfg: Config) -> bool:
        chord = cfg.hotkey.chord
        listener = HotkeyListener(chord, self.controller.post_toggle)
        try:
            listener.start()
        except HotkeyError as e:
            log.warning("%s", e)
            self.tray.show_message(TITLE, str(e))
            return False
        if self.hotkey:
            self.hotkey.stop()
        self.hotkey = listener
        self.controller.set_hotkey_text(chord.display)
        return True

    def _open_mic(self) -> None:
        try:
            self.recorder.open()
        except AudioError as e:
            self.tray.show_message(TITLE, str(e))

    # --- メニューとウィジェットから ---

    def open_settings(self) -> None:
        try:
            os.startfile(self.config_path)  # type: ignore[attr-defined]
        except OSError:
            subprocess.Popen(["notepad.exe", str(self.config_path)])

    def show_help(self) -> None:
        self.controller.show_message(
            f"{self.controller.hotkeyText} かマイクで開始 / 終了。閉じるボタンで録音を破棄",
            timeout_ms=5000,
        )

    def set_always_show(self, value: bool) -> None:
        if self._write_value("widget", "always_show", value):
            self.config.widget.always_show = value
        self.widget.set_always_show(value)

    def set_device(self, name: str) -> None:
        if self._write_value("audio", "device", name):
            audio = self.config.audio.model_copy(update={"device": name})
            self._apply_audio(self.config.model_copy(update={"audio": audio}))

    def _write_value(self, section: str, key: str, value: str | bool) -> bool:
        try:
            config.update_value(self.config_path, section, key, value)
        except (OSError, ConfigError) as e:
            self.tray.show_message(TITLE, f"設定ファイルに保存できません: {e}")
            return False
        return True

    def _apply_audio(self, new: Config) -> None:
        """マイクの設定を反映する。録音中なら次の録音から。"""
        old = self.config.audio
        self.config = new
        self.recorder.device = new.audio.device
        changed = old.device != new.audio.device or old.keep_open != new.audio.keep_open
        if not changed or self.recorder.recording:
            self.recorder.keep_open = new.audio.keep_open
            return
        self.recorder.close()
        self.recorder.keep_open = new.audio.keep_open
        if new.audio.keep_open:
            self._open_mic()

    def reload(self) -> None:
        try:
            new = config.load(self.config_path)
        except ConfigError as e:
            self.tray.show_message(TITLE, f"{e}\n前の設定のまま動作します")
            return
        old = self.config
        if new.hotkey.chord != old.hotkey.chord and not self._register_hotkey(new):
            new = new.model_copy(update={"hotkey": old.hotkey})
        self._apply_audio(new)
        self.widget.set_always_show(new.widget.always_show)
        self.tray.set_always_show(new.widget.always_show)
        message = "設定を再読み込みしました"
        if new.asr != old.asr:
            message += "。[asr] の変更は再起動後に反映されます"
        self.controller.show_message(message)
        self.widget.show()

    def quit(self) -> None:
        if self.hotkey:
            self.hotkey.stop()
        self.recorder.close()
        self.recognizer.stop()
        self.injector.stop()
        self.tray.hide()
        self._qapp.quit()
