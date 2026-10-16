from kotoba_desktop.config import InjectConfig, InjectProfile
from kotoba_desktop.inject.profiles import resolve


def test_windows_terminal_uses_shift_insert() -> None:
    p = resolve(InjectConfig(), "keep", "WindowsTerminal.exe", "CASCADIA_HOSTING_WINDOW_CLASS")
    assert str(p.paste_key) == "shift+insert"
    assert p.method == "paste"
    assert p.restore_delay_ms == 300


def test_process_match_ignores_case() -> None:
    p = resolve(InjectConfig(), "keep", "windowsterminal.EXE", "")
    assert str(p.paste_key) == "shift+insert"


def test_console_by_class() -> None:
    p = resolve(InjectConfig(), "keep", "cmd.exe", "ConsoleWindowClass")
    assert str(p.paste_key) == "shift+insert"


def test_other_apps_use_default() -> None:
    p = resolve(InjectConfig(), "strip", "Cursor.exe", "Chrome_WidgetWin_1")
    assert str(p.paste_key) == "ctrl+v"
    assert p.punctuation == "strip"


def test_profile_overrides_only_given_fields() -> None:
    cfg = InjectConfig(
        profile=[InjectProfile(match_process="slack.exe", method="type", punctuation="strip")]
    )
    p = resolve(cfg, "keep", "slack.exe", "")
    assert p.method == "type"
    assert p.punctuation == "strip"
    assert str(p.paste_key) == "ctrl+v"


def test_both_matchers_must_match() -> None:
    cfg = InjectConfig(
        profile=[InjectProfile(match_process="a.exe", match_class="X", paste_key="shift+insert")]
    )
    assert str(resolve(cfg, "keep", "a.exe", "Y").paste_key) == "ctrl+v"
    assert str(resolve(cfg, "keep", "a.exe", "X").paste_key) == "shift+insert"
