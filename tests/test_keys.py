import pytest

from kotoba_desktop.keys import parse_chord


def test_parse_ctrl_h() -> None:
    chord = parse_chord("ctrl+h")
    assert chord.modifiers == ("ctrl",)
    assert chord.vk == ord("H")
    assert chord.hotkey_flags == 0x2  # MOD_CONTROL
    assert str(chord) == "ctrl+h"


def test_parse_normalizes_case_order_and_aliases() -> None:
    chord = parse_chord("Shift + Control + INS")
    assert chord.modifiers == ("ctrl", "shift")
    assert chord.vk == 0x2D
    assert str(chord) == "ctrl+shift+insert"


def test_single_key_without_modifier() -> None:
    chord = parse_chord("nonconvert")
    assert chord.modifiers == ()
    assert chord.vk == 0x1D
    assert chord.hotkey_flags == 0


def test_key_events_press_then_release_in_reverse() -> None:
    events = parse_chord("ctrl+shift+v").key_events()
    assert events == [
        (0x11, False),
        (0x10, False),
        (ord("V"), False),
        (ord("V"), True),
        (0x10, True),
        (0x11, True),
    ]


@pytest.mark.parametrize("text", ["", "ctrl+", "ctrl", "foo+h", "ctrl+ctrl+h", "ctrl+unknown"])
def test_invalid(text: str) -> None:
    with pytest.raises(ValueError):
        parse_chord(text)


def test_display() -> None:
    assert parse_chord("ctrl+h").display == "Ctrl+H"
    assert parse_chord("shift+insert").display == "Shift+Insert"
    assert parse_chord("ctrl+alt+f11").display == "Ctrl+Alt+F11"
