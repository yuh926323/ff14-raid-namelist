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
        token = _clean_env_value(os.environ.get("DISCORD_BOT_TOKEN"))
        channel_id = _clean_env_value(os.environ.get("DISCORD_CHANNEL_ID"))
        if not token:
            raise ValueError("DISCORD_BOT_TOKEN is required")
        if _is_placeholder(token) or not _looks_like_bot_token(token):
            raise ValueError(
                "DISCORD_BOT_TOKEN does not look like a Discord bot token. "
                "Use Discord Developer Portal -> your application -> Bot -> Reset Token; "
                "do not use Client Secret, Application ID, or Public Key."
            )
        if not channel_id:
            raise ValueError("DISCORD_CHANNEL_ID is required")

        return cls(
            token=token,
            channel_id=int(channel_id),
            data_path=Path(os.environ.get("NAMELIST_DATA_PATH", "bot-data.json")),
            output_path=Path(os.environ.get("NAMELIST_OUTPUT_PATH", "namelist.json")),
            guild_id=_optional_int(_clean_env_value(os.environ.get("DISCORD_GUILD_ID"))),
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

    class RecentRecordsView(discord.ui.View):
        def __init__(
            self,
            *,
            records: list[dict[str, Any]],
            rating: str | None,
            page: int,
            page_size: int,
            user_id: int,
        ) -> None:
            super().__init__(timeout=300)
            self.records = records
            self.rating = rating
            self.page_size = _clamp_page_size(page_size)
            self.user_id = user_id
            self.page = _clamp_page(page, len(records), self.page_size)
            self._sync_buttons()

        async def interaction_check(self, interaction: discord.Interaction) -> bool:
            if interaction.user.id == self.user_id:
                return True

            await interaction.response.send_message(
                "Only the user who ran `/recent` can use these buttons.",
                ephemeral=True,
            )
            return False

        @discord.ui.button(label="上一頁", style=discord.ButtonStyle.secondary)
        async def previous_page(
            self,
            interaction: discord.Interaction,
            button: discord.ui.Button,
        ) -> None:
            self.page = max(1, self.page - 1)
            self._sync_buttons()
            await interaction.response.edit_message(content=self.content(), view=self)

        @discord.ui.button(label="下一頁", style=discord.ButtonStyle.primary)
        async def next_page(
            self,
            interaction: discord.Interaction,
            button: discord.ui.Button,
        ) -> None:
            self.page = min(self.total_pages, self.page + 1)
            self._sync_buttons()
            await interaction.response.edit_message(content=self.content(), view=self)

        @property
        def total_pages(self) -> int:
            return _total_pages(len(self.records), self.page_size)

        def content(self) -> str:
            return _format_recent_response(
                self.records,
                rating=self.rating,
                page=self.page,
                page_size=self.page_size,
            )

        def _sync_buttons(self) -> None:
            previous_button = self._button("上一頁")
            next_button = self._button("下一頁")
            if previous_button is not None:
                previous_button.disabled = self.page <= 1
            if next_button is not None:
                next_button.disabled = self.page >= self.total_pages

        def _button(self, label: str) -> discord.ui.Button | None:
            for child in self.children:
                if isinstance(child, discord.ui.Button) and child.label == label:
                    return child
            return None

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

    @bot.tree.command(name="recent", description="Show recently added namelist records.")
    @app_commands.describe(
        rating="Filter by rating.",
        page="Page number, starting from 1.",
        page_size="Records per page, from 1 to 10.",
    )
    @app_commands.choices(
        rating=[
            app_commands.Choice(name="✅ good", value="good"),
            app_commands.Choice(name="❌ bad", value="bad"),
        ]
    )
    async def recent_command(
        interaction: discord.Interaction,
        rating: str | None = None,
        page: int = 1,
        page_size: int = 8,
    ) -> None:
        summary = bot.store.write_summary(settings.output_path)
        records = _recent_records(summary, rating=rating)
        if not records:
            await interaction.response.send_message(
                _format_recent_response(records, rating=rating, page=page, page_size=page_size),
                ephemeral=True,
            )
            return

        view = RecentRecordsView(
            records=records,
            rating=rating,
            page=page,
            page_size=page_size,
            user_id=interaction.user.id,
        )
        await interaction.response.send_message(
            view.content(),
            view=view if view.total_pages > 1 else None,
            ephemeral=True,
        )

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
    if not content:
        return False
    return any(
        line.strip().startswith((GOOD_MARKER, BAD_MARKER))
        for line in content.splitlines()
    )


def _recent_records(
    summary: dict[str, Any],
    *,
    rating: str | None = None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for player in summary.get("players", []):
        for evidence in player.get("evidence", []):
            if rating is not None and evidence.get("rating") != rating:
                continue

            records.append(
                {
                    "key": player.get("key"),
                    "name": player.get("name"),
                    "world": player.get("world"),
                    "rating": evidence.get("rating"),
                    "timestamp": evidence.get("timestamp"),
                    "author": evidence.get("author"),
                    "reason": evidence.get("reason"),
                    "text": evidence.get("text"),
                    "message_id": evidence.get("message_id"),
                }
            )

    return sorted(
        records,
        key=lambda record: (record.get("timestamp") or "", record.get("message_id") or ""),
        reverse=True,
    )


def _format_recent_response(
    records: list[dict[str, Any]],
    *,
    rating: str | None,
    page: int,
    page_size: int,
) -> str:
    page_size = _clamp_page_size(page_size)
    total = len(records)
    total_pages = _total_pages(total, page_size)
    page = _clamp_page(page, total, page_size)
    label = _rating_label(rating) if rating else "all"

    if total == 0:
        return f"No recent records for `{label}`."

    start = (page - 1) * page_size
    current_records = records[start : start + page_size]
    lines = [f"Recent records `{label}` page {page}/{total_pages} ({total} total)"]

    for offset, record in enumerate(current_records, start=start + 1):
        marker = _rating_marker(record.get("rating"))
        key = record.get("key") or record.get("name") or "unknown player"
        author = record.get("author") or "unknown author"
        timestamp = _short_timestamp(record.get("timestamp"))
        reason = record.get("reason") or record.get("text") or ""
        reason_text = f" - {_truncate(str(reason), 100)}" if reason else ""
        lines.append(f"{offset}. {marker} `{key}` by {author} at {timestamp}{reason_text}")

    return "\n".join(lines)


def _clamp_page(page: int, total_records: int, page_size: int) -> int:
    return min(max(1, page), _total_pages(total_records, page_size))


def _clamp_page_size(page_size: int) -> int:
    return min(10, max(1, page_size))


def _total_pages(total_records: int, page_size: int) -> int:
    return max(1, (total_records + page_size - 1) // page_size)


def _rating_marker(rating: Any) -> str:
    if rating == "good":
        return GOOD_MARKER
    if rating == "bad":
        return BAD_MARKER
    return "?"


def _rating_label(rating: str | None) -> str:
    if rating == "good":
        return f"{GOOD_MARKER} good"
    if rating == "bad":
        return f"{BAD_MARKER} bad"
    return "all"


def _short_timestamp(timestamp: Any) -> str:
    if not timestamp:
        return "unknown time"
    value = str(timestamp)
    return value.replace("T", " ")[:16]


def _truncate(value: str, length: int) -> str:
    if len(value) <= length:
        return value
    return value[: length - 3].rstrip() + "..."


def _optional_int(value: str | None) -> int | None:
    if not value:
        return None
    return int(value)


def _clean_env_value(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"'}:
        cleaned = cleaned[1:-1].strip()
    return cleaned


def _is_placeholder(value: str) -> bool:
    return value.startswith("replace-with-")


def _looks_like_bot_token(value: str) -> bool:
    return len(value) >= 50 and "." in value and " " not in value


if __name__ == "__main__":
    raise SystemExit(main())
