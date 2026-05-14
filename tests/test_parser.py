from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ff14_raid_namelist.cli import main
from ff14_raid_namelist.parser import extract_mentions, summarize_export


def message(
    content: str,
    *,
    message_id: str,
    timestamp: str = "2026-05-14T10:00:00+00:00",
    author: str = "note-taker",
) -> dict:
    return {
        "id": message_id,
        "timestamp": timestamp,
        "content": content,
        "author": {"name": author},
    }


def summarize(messages: list[dict]) -> dict:
    return summarize_export(
        {"messages": messages},
        input_path="channel.json",
        generated_at="2026-05-14T00:00:00Z",
    )


def test_ignores_chat_without_rating_markers() -> None:
    result = summarize(
        [
            message("今天這場打得不錯，晚點再排", message_id="1"),
            message("Maybe Tomorrow", message_id="2"),
        ]
    )

    assert result["players"] == []
    assert result["unparsed"] == []
    assert result["source"]["total_messages"] == 2
    assert result["source"]["skipped_messages"] == 2


def test_accumulates_good_and_bad_for_same_player_with_world() -> None:
    result = summarize(
        [
            message("✅ Alpha Beta@Tonberry", message_id="1"),
            message(
                "❌ Alpha Beta@Tonberry",
                message_id="2",
                timestamp="2026-05-14T11:00:00+00:00",
            ),
        ]
    )

    assert len(result["players"]) == 1
    player = result["players"][0]
    assert player["key"] == "Alpha Beta@Tonberry"
    assert player["name"] == "Alpha Beta"
    assert player["world"] == "Tonberry"
    assert player["needs_world_review"] is False
    assert player["count"] == 2
    assert player["good_count"] == 1
    assert player["bad_count"] == 1
    assert player["score"] == 0
    assert player["last_seen"] == "2026-05-14T11:00:00+00:00"
    assert [evidence["rating"] for evidence in player["evidence"]] == ["good", "bad"]


def test_name_only_records_merge_into_single_known_world_and_mark_review() -> None:
    result = summarize(
        [
            message("✅ Alpha Beta", message_id="1"),
            message("❌ Alpha Beta@Tonberry", message_id="2"),
        ]
    )

    assert len(result["players"]) == 1
    player = result["players"][0]
    assert player["key"] == "Alpha Beta@Tonberry"
    assert player["needs_world_review"] is True
    assert player["good_count"] == 1
    assert player["bad_count"] == 1


def test_name_only_records_stay_separate_when_multiple_worlds_are_known() -> None:
    result = summarize(
        [
            message("✅ Alpha Beta@Tonberry", message_id="1"),
            message("✅ Alpha Beta@Kujata", message_id="2"),
            message("❌ Alpha Beta", message_id="3"),
        ]
    )

    players = {player["key"]: player for player in result["players"]}
    assert set(players) == {"Alpha Beta", "Alpha Beta@Kujata", "Alpha Beta@Tonberry"}
    assert players["Alpha Beta"]["needs_world_review"] is True
    assert players["Alpha Beta"]["bad_count"] == 1
    assert players["Alpha Beta"]["evidence"][0]["reason"] == ""


def test_line_with_both_rating_markers_goes_to_unparsed() -> None:
    result = summarize([message("✅ Alpha Beta ❌ Gamma Delta", message_id="1")])

    assert result["players"] == []
    assert result["source"]["unparsed_records"] == 1
    assert result["unparsed"][0]["reason"] == "mixed_rating_markers"


def test_full_width_at_parenthesized_world_and_multiple_players() -> None:
    mentions = extract_mentions("✅ Gamma Delta＠Kujata, Epsilon Zeta (Mandragora)")

    assert mentions[0].name == "Gamma Delta"
    assert mentions[0].world == "Kujata"
    assert mentions[1].name == "Epsilon Zeta"
    assert mentions[1].world == "Mandragora"

    result = summarize(
        [message("✅ Gamma Delta＠Kujata, Epsilon Zeta (Mandragora)", message_id="1")]
    )
    players = {player["key"]: player for player in result["players"]}
    assert set(players) == {"Epsilon Zeta@Mandragora", "Gamma Delta@Kujata"}
    assert all(player["good_count"] == 1 for player in players.values())


def test_tw_world_at_separator_and_reason_are_parsed() -> None:
    result = summarize(
        [
            message(
                "❌ Auotzu@迦樓羅：開了招募說打兩把幻白虎，結果打一把人就跑掉了",
                message_id="1",
                author="reporter",
            )
        ]
    )

    assert len(result["players"]) == 1
    player = result["players"][0]
    assert player["key"] == "Auotzu@迦樓羅"
    assert player["world"] == "迦樓羅"
    assert player["count"] == 1
    assert player["evidence"][0]["author"] == "reporter"
    assert player["evidence"][0]["reason"] == "開了招募說打兩把幻白虎，結果打一把人就跑掉了"
    assert result["world_counts"] == [
        {"world": "迦樓羅", "needs_world_review": False, "count": 1}
    ]


def test_tw_world_space_colon_and_parentheses_separators_are_parsed() -> None:
    result = summarize(
        [
            message("✅ 圓舞 鳳凰 白魔表現很好", message_id="1"),
            message("✅ 幼小的蘿莉：伊弗利特 畫家輸出很好", message_id="2"),
            message("❌ 濃綠茶（奧汀）走位失誤", message_id="3"),
        ]
    )

    players = {player["key"]: player for player in result["players"]}
    assert players["圓舞@鳳凰"]["evidence"][0]["reason"] == "白魔表現很好"
    assert players["幼小的蘿莉@伊弗利特"]["evidence"][0]["reason"] == "畫家輸出很好"
    assert players["濃綠茶@奧汀"]["evidence"][0]["reason"] == "走位失誤"


def test_message_not_starting_with_rating_marker_is_skipped_even_if_marker_exists() -> None:
    result = summarize(
        [
            message("幻白虎 MT騎士 傷害很低 | ❌黑貓金漸層@利維坦", message_id="1"),
        ]
    )

    assert result["players"] == []
    assert result["unparsed"] == []
    assert result["source"]["skipped_messages"] == 1


def test_multiple_leading_rating_entries_are_split_by_marker_segments() -> None:
    result = summarize(
        [
            message("❌Retys  | ❌森亞 | ❌清風清夢 | ❌檸檬可麗露", message_id="1"),
        ]
    )

    players = {player["key"]: player for player in result["players"]}
    assert set(players) == {"Retys", "森亞", "清風清夢", "檸檬可麗露"}
    assert all(player["bad_count"] == 1 for player in players.values())
    assert all(player["needs_world_review"] is True for player in players.values())
    assert all(player["evidence"][0]["reason"] == "" for player in players.values())


def test_tw_world_aliases_are_canonicalized() -> None:
    result = summarize(
        [
            message("✅ 小火 火神 表現穩定", message_id="1"),
            message("✅ 小水@水神 補量很好", message_id="2"),
            message("❌ 小風（風神）常常貪刀", message_id="3"),
            message("❌ 小土：土神 沒開減傷", message_id="4"),
        ]
    )

    players = {player["key"]: player for player in result["players"]}
    assert players["小火@伊弗利特"]["world"] == "伊弗利特"
    assert players["小水@利維坦"]["world"] == "利維坦"
    assert players["小風@迦樓羅"]["world"] == "迦樓羅"
    assert players["小土@泰坦"]["world"] == "泰坦"


def test_unknown_tw_world_like_text_is_kept_as_reason_not_world() -> None:
    result = summarize([message("❌ 安冏 (澳丁)心態不是很好", message_id="1")])

    assert len(result["players"]) == 1
    player = result["players"][0]
    assert player["key"] == "安冏"
    assert player["world"] is None
    assert player["needs_world_review"] is True
    assert player["evidence"][0]["reason"] == "(澳丁)心態不是很好"


def test_cli_writes_json_output() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        input_path = Path(temp_dir) / "channel.json"
        output_path = Path(temp_dir) / "namelist.json"
        input_path.write_text(
            json.dumps({"messages": [message("✅ Alpha Beta@Tonberry", message_id="1")]}),
            encoding="utf-8",
        )

        exit_code = main(["--input", str(input_path), "--output", str(output_path), "--pretty"])

        assert exit_code == 0
        output = json.loads(output_path.read_text(encoding="utf-8"))
        assert output["players"][0]["key"] == "Alpha Beta@Tonberry"


def load_tests(
    loader: unittest.TestLoader,
    tests: unittest.TestSuite,
    pattern: str | None,
) -> unittest.TestSuite:
    suite = unittest.TestSuite()
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            suite.addTest(unittest.FunctionTestCase(value))
    return suite


if __name__ == "__main__":
    unittest.main()
