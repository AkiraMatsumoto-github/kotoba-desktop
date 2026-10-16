from collections.abc import Callable
from dataclasses import dataclass, field

import pytest

from kotoba_desktop.config import Config
from kotoba_desktop.inject.injector import Backend, Injector, Result, Status
from kotoba_desktop.inject.paste import TargetChanged
from kotoba_desktop.keys import Chord
from kotoba_desktop.win32.window import WindowInfo

TERMINAL = WindowInfo(1, 100, "WindowsTerminal.exe", "CASCADIA_HOSTING_WINDOW_CLASS", False)
CURSOR = WindowInfo(2, 200, "Cursor.exe", "Chrome_WidgetWin_1", False)
ADMIN = WindowInfo(3, 300, "mmc.exe", "MMCMainFrame", True)


@dataclass
class Fake:
    window: WindowInfo | None = CURSOR
    pressed: list[bool] = field(default_factory=list)  # modifiers_pressed が順に返す値
    pasted: list[tuple[str, str, int]] = field(default_factory=list)
    typed: list[tuple[int, str]] = field(default_factory=list)
    clipboard: list[str] = field(default_factory=list)
    note: str = ""  # paste が返す補足
    switch_to: WindowInfo | None = None  # paste の直前に前面をこれに変える

    def backend(self, self_elevated: bool = False) -> Backend:
        def paste(text: str, key: Chord, delay: int, still_target: Callable[[], bool]) -> str:
            if self.switch_to is not None:
                self.window = self.switch_to
            if not still_target():
                raise TargetChanged
            self.pasted.append((text, str(key), delay))
            return self.note

        return Backend(
            foreground=lambda: self.window,
            modifiers_pressed=lambda: self.pressed.pop(0) if self.pressed else False,
            paste=paste,
            type_text=lambda hwnd, text: self.typed.append((hwnd, text)),
            set_clipboard=self.clipboard.append,
            self_elevated=self_elevated,
            self_pid=999,
        )


def make(fake: Fake, cfg: Config | None = None, self_elevated: bool = False) -> Injector:
    return Injector(lambda: cfg or Config(), lambda r: None, fake.backend(self_elevated))


def test_paste_with_profile_key() -> None:
    fake = Fake(window=TERMINAL)
    result = make(fake).inject("ls を実行\n")
    assert result.status is Status.INJECTED
    assert fake.pasted == [("ls を実行", "shift+insert", 300)]


def test_waits_for_modifiers_release() -> None:
    fake = Fake(pressed=[True, True, False])
    assert make(fake).inject("テスト").status is Status.INJECTED
    assert fake.pressed == []


def test_modifier_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("kotoba_desktop.inject.injector.MODIFIER_TIMEOUT_S", 0.05)
    fake = Fake(pressed=[True] * 1000)
    result = make(fake).inject("テスト")
    assert result == Result("テスト", Status.MODIFIER_TIMEOUT)
    assert fake.pasted == []


def test_empty_after_postprocess() -> None:
    fake = Fake()
    assert make(fake).inject("ご視聴ありがとうございました").status is Status.EMPTY
    assert make(fake).inject(" \n").status is Status.EMPTY
    assert fake.pasted == []


def test_elevated_window_gets_clipboard_only() -> None:
    fake = Fake(window=ADMIN)
    result = make(fake).inject("管理者")
    assert result.status is Status.CLIPBOARD_ONLY
    assert fake.clipboard == ["管理者"]
    assert fake.pasted == []


def test_elevated_window_ok_when_self_elevated() -> None:
    fake = Fake(window=ADMIN)
    assert make(fake, self_elevated=True).inject("管理者").status is Status.INJECTED


def test_own_window_gets_clipboard_only() -> None:
    fake = Fake(window=WindowInfo(9, 999, "python.exe", "Qt", False))
    assert make(fake).inject("自分").status is Status.CLIPBOARD_ONLY


def test_no_window_gets_clipboard_only() -> None:
    fake = Fake(window=None)
    assert make(fake).inject("なし").status is Status.CLIPBOARD_ONLY


def test_processed_text_is_not_postprocessed() -> None:
    cfg = Config.model_validate({"text": {"replace": {"A": "AA"}}})
    fake = Fake()
    make(fake, cfg).inject("A", processed=True)
    make(fake, cfg).inject("A")
    assert [t for t, _, _ in fake.pasted] == ["A", "AA"]


def test_type_method() -> None:
    cfg = Config.model_validate({"inject": {"method": "type"}})
    fake = Fake()
    assert make(fake, cfg).inject("打鍵").status is Status.INJECTED
    assert fake.typed == [(2, "打鍵")]


def test_restore_note_is_reported() -> None:
    fake = Fake(note="元に戻していません")
    result = make(fake).inject("テスト")
    assert result.status is Status.INJECTED
    assert "元に戻していません" in result.detail


def test_target_changed_before_paste_goes_to_clipboard() -> None:
    fake = Fake(window=CURSOR, switch_to=TERMINAL)
    result = make(fake).inject("切替")
    assert result.status is Status.CLIPBOARD_ONLY
    assert fake.pasted == []
    assert fake.clipboard == ["切替"]


def test_reinject_target_must_be_foreground() -> None:
    fake = Fake(window=CURSOR)
    assert make(fake).inject("再", processed=True, target=TERMINAL.hwnd).status is (
        Status.CLIPBOARD_ONLY
    )
    assert make(fake).inject("再", processed=True, target=CURSOR.hwnd).status is Status.INJECTED


def test_thread_keeps_order() -> None:
    fake = Fake()
    results: list[Result] = []
    inj = Injector(Config, results.append, fake.backend())
    inj.start()
    for i in range(20):
        inj.submit(f"文{i}")
    inj.stop()
    assert [t for t, _, _ in fake.pasted] == [f"文{i}" for i in range(20)]
    assert all(r.status is Status.INJECTED for r in results)


def test_thread_survives_errors() -> None:
    fake = Fake()
    results: list[Result] = []
    backend = fake.backend()
    calls = iter([RuntimeError("boom")])

    def flaky(*args: object) -> str:
        if (e := next(calls, None)) is not None:
            raise e
        return ""

    backend.paste = flaky
    inj = Injector(Config, results.append, backend)
    inj.start()
    inj.submit("1")
    inj.submit("2")
    inj.stop()
    assert [r.status for r in results] == [Status.ERROR, Status.INJECTED]


def test_error_result_has_postprocessed_text() -> None:
    """例外のときも履歴に入るのは後処理済みの文字列（再入力は後処理をかけないため）。"""
    cfg = Config.model_validate({"text": {"replace": {"クロード": "Claude"}}})
    fake = Fake()
    backend = fake.backend()

    def boom(*args: object) -> str:
        raise RuntimeError("boom")

    backend.paste = boom
    results: list[Result] = []
    inj = Injector(lambda: cfg, results.append, backend)
    inj.start()
    inj.submit("クロード\n")
    inj.stop()
    assert results == [Result("Claude", Status.ERROR, "boom")]
