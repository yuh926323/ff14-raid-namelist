from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from ff14_raid_namelist.bot import BotSettings


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


if __name__ == "__main__":
    unittest.main()
