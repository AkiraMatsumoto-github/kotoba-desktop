"""部品を組み立て、設定の反映や終了を受け持つ。"""

import logging
import os
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
from kotoba_desktop.ui.settings import SettingsDialog
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

        self.tray.settingsDialogRequested.connect(self.open_settings_dialog)
        self.tray.quitRequested.connect(self.quit)
        self.tray.showWidgetRequested.connect(self.widget.show)
        self.tray.alwaysShowToggled.connect(self.set_always_show)
        self.tray.deviceSelected.connect(self.set_device)

        if startup_error:
            self.tray.show_message(TITLE, startup_error)
        self.hotkey: HotkeyListener | None = None
        self._settings: SettingsDialog | None = None
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
                TITLE, "モデルをダウンロードしています（初回のみ、約 1.6 GB）"
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

    def open_settings_dialog(self) -> None:
        if self._settings is not None:
            self._settings.raise_()
            self._settings.activateWindow()
            return
        # キーを押して選ぶ間は今のホットキーを外す（外さないと押した瞬間に録音が始まる）
        if self.hotkey:
            self.hotkey.stop()
            self.hotkey = None
        try:
            devices = input_devices()
        except Exception:
            log.warning("マイクの一覧を取得できません", exc_info=True)
            devices = []
        self._settings = SettingsDialog(self.config, devices, self.apply_config)
        self._settings.finished.connect(self._on_settings_closed)
        self._settings.show()
        self._settings.raise_()
        self._settings.activateWindow()

    def _on_settings_closed(self) -> None:
        self._settings = None
        if self.hotkey is None:  # キャンセルしたときは元のキーに戻す
            self._register_hotkey(self.config)

    def apply_config(self, new: Config) -> str:
        """設定を反映して保存する。反映できなければエラーメッセージを返す（設定はそのまま）。"""
        chord = new.hotkey.chord
        if self.hotkey is None or chord != self.hotkey.chord:
            listener = HotkeyListener(chord, self.controller.post_toggle)
            try:
                listener.start()
            except HotkeyError:
                return f"{chord.display} は Windows か他のアプリが使っているため登録できません"
            if self.hotkey:
                self.hotkey.stop()
            self.hotkey = listener
            self.controller.set_hotkey_text(chord.display)
        self._apply_audio(new)  # self.config もここで新しい設定になる
        self.widget.set_always_show(new.widget.always_show)
        self.tray.set_always_show(new.widget.always_show)
        try:
            config.save(new, self.config_path)
        except (OSError, ConfigError) as e:
            self.tray.show_message(TITLE, f"設定を保存できません（今回の起動中だけ有効です）: {e}")
        return ""

    def set_always_show(self, value: bool) -> None:
        widget = self.config.widget.model_copy(update={"always_show": value})
        self.apply_config(self.config.model_copy(update={"widget": widget}))

    def set_device(self, name: str) -> None:
        audio = self.config.audio.model_copy(update={"device": name})
        self.apply_config(self.config.model_copy(update={"audio": audio}))

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

    def quit(self) -> None:
        if self.hotkey:
            self.hotkey.stop()
        self.recorder.close()
        self.recognizer.stop()
        self.injector.stop()
        self.tray.hide()
        self._qapp.quit()
