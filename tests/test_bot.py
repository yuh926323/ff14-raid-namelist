from __future__ import annotations

import unittest

from ff14_raid_namelist.bot import (
    _format_recent_record_details,
    _format_recent_response,
    _summary_stats,
)


class BotFormattingTests(unittest.TestCase):
    def test_recent_record_details_omit_reason_when_blank(self) -> None:
        details = _format_recent_record_details(
            {
                "author": "note-taker",
                "timestamp": "2026-05-15T10:30:00+00:00",
                "reason": "",
                "text": "❌ 清風清夢",
                "count": 2,
                "good_count": 0,
                "bad_count": 2,
                "score": -2,
            },
            reason_length=180,
        )

        self.assertIn("加入者：note-taker", details)
        self.assertIn("累計：✅ 0 / ❌ 2（共 2，分數 -2）", details)
        self.assertNotIn("理由：", details)
        self.assertNotIn("❌ 清風清夢", details)

    def test_recent_record_details_include_reason_when_present(self) -> None:
        details = _format_recent_record_details(
            {
                "author": "note-taker",
                "timestamp": "2026-05-15T10:30:00+00:00",
                "reason": "進度詐欺",
                "count": 1,
                "good_count": 0,
                "bad_count": 1,
                "score": -1,
            },
            reason_length=180,
        )

        self.assertIn("理由：進度詐欺", details)

    def test_recent_text_response_includes_counts_without_text_fallback(self) -> None:
        response = _format_recent_response(
            [
                {
                    "key": "清風清夢",
                    "rating": "bad",
                    "author": "note-taker",
                    "timestamp": "2026-05-15T10:30:00+00:00",
                    "reason": "",
                    "text": "❌ 清風清夢",
                    "count": 2,
                    "good_count": 0,
                    "bad_count": 2,
                    "score": -2,
                }
            ],
            rating="bad",
            page=1,
            page_size=8,
        )

        self.assertIn("累計：✅ 0 / ❌ 2（共 2，分數 -2）", response)
        self.assertNotIn("❌ 清風清夢", response)

    def test_summary_stats_include_top_rating_players(self) -> None:
        stats = _summary_stats(
            {
                "source": {"parsed_records": 3, "unparsed_records": 0},
                "players": [
                    {
                        "key": "清風清夢",
                        "count": 2,
                        "good_count": 0,
                        "bad_count": 2,
                        "score": -2,
                        "last_seen": "2026-05-15T10:30:00+00:00",
                    },
                    {
                        "key": "可靠隊友@鳳凰",
                        "count": 1,
                        "good_count": 1,
                        "bad_count": 0,
                        "score": 1,
                        "last_seen": "2026-05-15T10:20:00+00:00",
                    },
                ],
            }
        )

        self.assertIn("清風清夢：✅ 0 / ❌ 2（分數 -2）", stats["top_bad_players"])
        self.assertIn("可靠隊友@鳳凰：✅ 1 / ❌ 0（分數 +1）", stats["top_good_players"])


if __name__ == "__main__":
    unittest.main()
