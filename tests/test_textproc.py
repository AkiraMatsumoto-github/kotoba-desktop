from kotoba_desktop.textproc import process


def test_drop_phrase_whole_match_only() -> None:
    drops = ["ご視聴ありがとうございました"]
    assert process("ご視聴ありがとうございました。", drop_phrases=drops) == ""
    assert process("本日はご視聴ありがとうございました", drop_phrases=drops) != ""


def test_newlines_removed_and_trimmed() -> None:
    assert process("  一行目\r\n二行目\n ") == "一行目二行目"


def test_fullwidth_alnum_to_halfwidth() -> None:
    assert process("ＷＳＬで１２３を") == "WSLで123を"
    # 全角の記号やカタカナはそのまま
    assert process("（テスト）") == "（テスト）"


def test_replace_in_order() -> None:
    assert process(
        "クロードコード", replace={"クロード": "Claude ", "Claude コード": "Claude Code"}
    ) == ("Claude Code")


def test_control_chars_from_replace_are_removed() -> None:
    # 置換辞書の値に改行やタブを書いても、ターミナルで Enter や補完にならない
    assert process("A", replace={"A": "1\n2\t3\x00"}) == "123"


def test_punctuation() -> None:
    assert process("はい、そうです。", punctuation="keep") == "はい、そうです。"
    assert process("はい、そうです。", punctuation="strip") == "はいそうです"
