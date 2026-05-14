from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .parser import BAD_MARKER, GOOD_MARKER
from .store import NamelistStore


@dataclass(frozen=True)
class BotSettings:
    token: str
    channel_id: int
    data_path: Path = Path("bot-data.json")
    output_path: Path = Path("namelist.json")
    guild_id: int | None = None

    @classmethod
    def from_env(cls) -> "BotSettings":
        token = os.environ.get("DISCORD_BOT_TOKEN")
        channel_id = os.environ.get("DISCORD_CHANNEL_ID")
        if not token:
            raise ValueError("DISCORD_BOT_TOKEN is required")
        if not channel_id:
            raise ValueError("DISCORD_CHANNEL_ID is required")

        return cls(
            token=token,
            channel_id=int(channel_id),
            data_path=Path(os.environ.get("NAMELIST_DATA_PATH", "bot-data.json")),
            output_path=Path(os.environ.get("NAMELIST_OUTPUT_PATH", "namelist.json")),
            guild_id=_optional_int(os.environ.get("DISCORD_GUILD_ID")),
        )


def main() -> int:
    try:
        settings = BotSettings.from_env()
        bot = create_bot(settings)
        bot.run(settings.token)
    except ValueError as exc:
        print(f"error: {exc}")
        return 1
    return 0


def create_bot(settings: BotSettings):
    try:
        import discord
        from discord import app_commands
        from discord.ext import commands
    except ImportError as exc:
        raise ValueError(
            "discord.py is required for bot mode. Install with: python3 -m pip install -e .[bot]"
        ) from exc

    intents = discord.Intents.default()
    intents.message_content = True

    class RaidNamelistBot(commands.Bot):
        def __init__(self) -> None:
            super().__init__(command_prefix=commands.when_mentioned, intents=intents)
            self.store = NamelistStore.load(settings.data_path)
            self.store.channel_id = str(settings.channel_id)

        async def setup_hook(self) -> None:
            if settings.guild_id is not None:
                guild = discord.Object(id=settings.guild_id)
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
            else:
                await self.tree.sync()

        async def on_ready(self) -> None:
            summary = self.store.write_summary(settings.output_path)
            print(
                f"Logged in as {self.user}. "
                f"Tracking channel {settings.channel_id}. "
                f"{len(summary['players'])} players loaded."
            )

        async def on_message(self, message: discord.Message) -> None:
            if message.author.id == self.user.id:
                return
            if message.channel.id != settings.channel_id:
                return
            if not _has_rating_marker(message.content):
                return

            self.store.upsert_message(_discord_message_record(message))
            self.store.save()
            self.store.write_summary(settings.output_path)

        async def on_message_edit(
            self,
            before: discord.Message,
            after: discord.Message,
        ) -> None:
            if after.channel.id != settings.channel_id:
                return

            if _has_rating_marker(after.content):
                self.store.upsert_message(_discord_message_record(after))
            else:
                self.store.remove_message(after.id)

            self.store.save()
            self.store.write_summary(settings.output_path)

        async def on_message_delete(self, message: discord.Message) -> None:
            if message.channel.id != settings.channel_id:
                return
            if self.store.remove_message(message.id):
                self.store.save()
                self.store.write_summary(settings.output_path)

    bot = RaidNamelistBot()

    @bot.tree.command(name="summary", description="Show the current FF14 namelist summary.")
    async def summary_command(interaction: discord.Interaction) -> None:
        summary = bot.store.write_summary(settings.output_path)
        source = summary["source"]
        await interaction.response.send_message(
            (
                f"Players: {len(summary['players'])}\n"
                f"Parsed records: {source['parsed_records']}\n"
                f"Unparsed records: {source['unparsed_records']}\n"
                f"Output: `{settings.output_path}`"
            ),
            ephemeral=True,
        )

    @bot.tree.command(name="export", description="Rewrite the namelist JSON output file.")
    async def export_command(interaction: discord.Interaction) -> None:
        summary = bot.store.write_summary(settings.output_path)
        await interaction.response.send_message(
            f"Wrote `{settings.output_path}` with {len(summary['players'])} players.",
            ephemeral=True,
        )

    @bot.tree.command(name="unparsed", description="Show recently unparsed rating messages.")
    async def unparsed_command(interaction: discord.Interaction) -> None:
        summary = bot.store.write_summary(settings.output_path)
        records = summary["unparsed"][-5:]
        if not records:
            await interaction.response.send_message("No unparsed records.", ephemeral=True)
            return

        lines = [
            f"- `{record['reason']}` {record['timestamp'] or 'unknown time'}: {record['text']}"
            for record in records
        ]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @bot.tree.command(name="scan", description="Scan the tracked channel history.")
    @app_commands.describe(limit="Maximum number of latest messages to scan. Leave empty for all.")
    async def scan_command(interaction: discord.Interaction, limit: int | None = None) -> None:
        if limit is not None and limit < 1:
            await interaction.response.send_message("Limit must be at least 1.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        channel = await _target_channel(bot, settings.channel_id)
        messages: list[dict[str, Any]] = []
        scanned = 0

        async for message in channel.history(limit=limit, oldest_first=True):
            scanned += 1
            if _has_rating_marker(message.content):
                messages.append(_discord_message_record(message))

        bot.store.replace_messages(messages, channel_id=settings.channel_id)
        bot.store.save()
        summary = bot.store.write_summary(settings.output_path)

        await interaction.followup.send(
            (
                f"Scanned {scanned} messages and tracked {len(messages)} rating messages.\n"
                f"Players: {len(summary['players'])}\n"
                f"Unparsed records: {summary['source']['unparsed_records']}\n"
                f"Output: `{settings.output_path}`"
            ),
            ephemeral=True,
        )

    return bot


def _discord_message_record(message: Any) -> dict[str, Any]:
    return {
        "id": str(message.id),
        "timestamp": message.created_at.isoformat(),
        "content": message.content,
        "author": {
            "id": str(message.author.id),
            "name": str(message.author),
            "username": getattr(message.author, "name", None),
            "nickname": getattr(message.author, "display_name", None),
        },
    }


async def _target_channel(bot: Any, channel_id: int) -> Any:
    channel = bot.get_channel(channel_id)
    if channel is None:
        channel = await bot.fetch_channel(channel_id)
    if not hasattr(channel, "history"):
        raise ValueError(f"channel {channel_id} does not support message history")
    return channel


def _has_rating_marker(content: str | None) -> bool:
    return bool(content) and (GOOD_MARKER in content or BAD_MARKER in content)


def _optional_int(value: str | None) -> int | None:
    if not value:
        return None
    return int(value)


if __name__ == "__main__":
    raise SystemExit(main())
