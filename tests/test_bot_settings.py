from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from ff14_raid_namelist.bot import (
    BotSettings,
    _clamp_page,
    _clamp_page_size,
    _format_recent_response,
    _has_rating_marker,
    _recent_records,
    _total_pages,
)


VALID_FAKE_TOKEN = "abc.defghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


class BotSettingsTests(unittest.TestCase):
    def test_rejects_short_token_that_does_not_look_like_bot_token(self) -> None:
        with patch.dict(
            os.environ,
            {
                "DISCORD_BOT_TOKEN": "short-client-secret-like-value",
                "DISCORD_CHANNEL_ID": "123",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "does not look like"):
                BotSettings.from_env()

    def test_rejects_placeholder_token(self) -> None:
        with patch.dict(
            os.environ,
            {
                "DISCORD_BOT_TOKEN": "replace-with-your-bot-token",
                "DISCORD_CHANNEL_ID": "123",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "does not look like"):
                BotSettings.from_env()

    def test_strips_outer_quotes_from_env_values(self) -> None:
        with patch.dict(
            os.environ,
            {
                "DISCORD_BOT_TOKEN": f"'{VALID_FAKE_TOKEN}'",
                "DISCORD_CHANNEL_ID": '"123"',
                "DISCORD_GUILD_ID": "'456'",
            },
            clear=True,
        ):
            settings = BotSettings.from_env()

        self.assertEqual(settings.token, VALID_FAKE_TOKEN)
        self.assertEqual(settings.channel_id, 123)
        self.assertEqual(settings.guild_id, 456)


class BotRecentCommandTests(unittest.TestCase):
    def test_has_rating_marker_requires_line_start_marker(self) -> None:
        self.assertTrue(_has_rating_marker("❌ Alpha Beta@Tonberry"))
        self.assertTrue(_has_rating_marker("hello\n✅ Alpha Beta@Tonberry"))
        self.assertFalse(_has_rating_marker("hello ❌ Alpha Beta@Tonberry"))

    def test_recent_records_filter_and_paginate(self) -> None:
        summary = {
            "players": [
                {
                    "key": "Alpha Beta@Tonberry",
                    "name": "Alpha Beta",
                    "world": "Tonberry",
                    "evidence": [
                        {
                            "message_id": "1",
                            "timestamp": "2026-05-14T10:00:00+00:00",
                            "author": "alice",
                            "rating": "good",
                            "reason": "nice clear",
                            "text": "✅ Alpha Beta@Tonberry nice clear",
                        }
                    ],
                },
                {
                    "key": "Gamma Delta@Kujata",
                    "name": "Gamma Delta",
                    "world": "Kujata",
                    "evidence": [
                        {
                            "message_id": "2",
                            "timestamp": "2026-05-14T11:00:00+00:00",
                            "author": "bob",
                            "rating": "bad",
                            "reason": "left after one pull",
                            "text": "❌ Gamma Delta@Kujata left after one pull",
                        }
                    ],
                },
            ]
        }

        records = _recent_records(summary, rating="bad")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["key"], "Gamma Delta@Kujata")

        response = _format_recent_response(records, rating="bad", page=1, page_size=1)
        self.assertIn("page 1/1", response)
        self.assertIn("❌ `Gamma Delta@Kujata` by bob", response)
        self.assertIn("left after one pull", response)

    def test_pagination_helpers_clamp_page_and_size(self) -> None:
        self.assertEqual(_clamp_page_size(0), 1)
        self.assertEqual(_clamp_page_size(99), 10)
        self.assertEqual(_total_pages(0, 8), 1)
        self.assertEqual(_total_pages(17, 8), 3)
        self.assertEqual(_clamp_page(-1, 17, 8), 1)
        self.assertEqual(_clamp_page(99, 17, 8), 3)


if __name__ == "__main__":
    unittest.main()
