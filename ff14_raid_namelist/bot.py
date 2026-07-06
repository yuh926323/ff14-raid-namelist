from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .parser import BAD_MARKER, GOOD_MARKER, record_content_lines
from .store import NamelistStore


@dataclass(frozen=True)
class BotSettings:
    token: str
    channel_id: int
    data_path: Path = Path("bot-data.json")
    output_path: Path = Path("namelist.json")
    guild_id: int | None = None
    scan_user_id: int | None = None
    reaction_role_channel_id: int | None = None
    reaction_role_message_id: int | None = None
    reaction_role_map: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "BotSettings":
        token = _clean_env_value(os.environ.get("DISCORD_BOT_TOKEN"))
        channel_id = _clean_env_value(os.environ.get("DISCORD_CHANNEL_ID"))
        scan_user_id = _clean_env_value(os.environ.get("DISCORD_SCAN_USER_ID"))
        reaction_role_channel_id = _optional_int(
            _clean_env_value(os.environ.get("DISCORD_REACTION_ROLE_CHANNEL_ID"))
        )
        reaction_role_message_id = _optional_int(
            _clean_env_value(os.environ.get("DISCORD_REACTION_ROLE_MESSAGE_ID"))
        )
        reaction_role_map = _reaction_role_map_from_env(
            _clean_env_value(os.environ.get("DISCORD_REACTION_ROLE_MAP"))
        )
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

        _validate_reaction_role_settings(
            channel_id=reaction_role_channel_id,
            message_id=reaction_role_message_id,
            role_map=reaction_role_map,
        )

        return cls(
            token=token,
            channel_id=int(channel_id),
            data_path=Path(os.environ.get("NAMELIST_DATA_PATH", "bot-data.json")),
            output_path=Path(os.environ.get("NAMELIST_OUTPUT_PATH", "namelist.json")),
            guild_id=_optional_int(_clean_env_value(os.environ.get("DISCORD_GUILD_ID"))),
            scan_user_id=_optional_int(scan_user_id),
            reaction_role_channel_id=reaction_role_channel_id,
            reaction_role_message_id=reaction_role_message_id,
            reaction_role_map=reaction_role_map,
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
    intents.reactions = True

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

        async def on_raw_reaction_add(
            self,
            payload: discord.RawReactionActionEvent,
        ) -> None:
            await self._sync_reaction_role(payload, adding=True)

        async def on_raw_reaction_remove(
            self,
            payload: discord.RawReactionActionEvent,
        ) -> None:
            await self._sync_reaction_role(payload, adding=False)

        async def _sync_reaction_role(
            self,
            payload: discord.RawReactionActionEvent,
            *,
            adding: bool,
        ) -> None:
            if not _is_reaction_role_payload(payload, settings):
                return
            if self.user is not None and payload.user_id == self.user.id:
                return
            if payload.guild_id is None:
                return

            role_id = settings.reaction_role_map.get(_reaction_role_emoji_key(payload.emoji))
            if role_id is None:
                return

            guild = self.get_guild(payload.guild_id)
            if guild is None:
                print(f"reaction role skipped: guild {payload.guild_id} is not in cache")
                return

            role = guild.get_role(role_id)
            if role is None:
                print(f"reaction role skipped: role {role_id} was not found")
                return

            member = await self._reaction_role_member(payload, guild)
            if member is None:
                return

            try:
                member_roles = getattr(member, "roles", [])
                if adding:
                    if role not in member_roles:
                        await member.add_roles(
                            role,
                            reason="Reaction role added from configured message",
                        )
                elif role in member_roles:
                    await member.remove_roles(
                        role,
                        reason="Reaction role removed from configured message",
                    )
            except (discord.Forbidden, discord.HTTPException) as exc:
                action = "add" if adding else "remove"
                print(f"reaction role failed to {action} role {role_id}: {exc}")

        async def _reaction_role_member(
            self,
            payload: discord.RawReactionActionEvent,
            guild: discord.Guild,
        ) -> discord.Member | None:
            member = getattr(payload, "member", None)
            if member is not None:
                return member

            member = guild.get_member(payload.user_id)
            if member is not None:
                return member

            try:
                return await guild.fetch_member(payload.user_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException) as exc:
                print(f"reaction role skipped: member {payload.user_id} was not found: {exc}")
                return None

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
                "只有執行 `/recent` 的使用者可以操作這組按鈕。",
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
            await interaction.response.edit_message(embed=self.embed(), view=self)

        @discord.ui.button(label="下一頁", style=discord.ButtonStyle.primary)
        async def next_page(
            self,
            interaction: discord.Interaction,
            button: discord.ui.Button,
        ) -> None:
            self.page = min(self.total_pages, self.page + 1)
            self._sync_buttons()
            await interaction.response.edit_message(embed=self.embed(), view=self)

        @property
        def total_pages(self) -> int:
            return _total_pages(len(self.records), self.page_size)

        def embed(self) -> discord.Embed:
            total = len(self.records)
            label = _rating_label(self.rating)
            embed = discord.Embed(
                title="近期加入名單",
                description=f"篩選：{label}｜第 {self.page}/{self.total_pages} 頁｜共 {total} 筆",
                color=_rating_color(self.rating),
            )

            start = (self.page - 1) * self.page_size
            for offset, record in enumerate(
                self.records[start : start + self.page_size],
                start=start + 1,
            ):
                marker = _rating_marker(record.get("rating"))
                key = record.get("key") or record.get("name") or "未知玩家"
                embed.add_field(
                    name=f"{offset}. {marker} {key}",
                    value=_format_recent_record_details(record, reason_length=180),
                    inline=False,
                )

            embed.set_footer(text="使用下方按鈕切換頁面，按鈕會在 5 分鐘後失效。")
            return embed

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

    async def ensure_target_command_channel(interaction: discord.Interaction) -> bool:
        if interaction.channel_id == settings.channel_id:
            return True

        await interaction.response.send_message(
            f"這個 Bot 只能在 <#{settings.channel_id}> 使用，請到指定頻道再執行指令。",
            ephemeral=True,
        )
        return False

    async def ensure_scan_user(interaction: discord.Interaction) -> bool:
        if settings.scan_user_id is None or interaction.user.id == settings.scan_user_id:
            return True

        await interaction.response.send_message(
            "只有指定的名單管理者可以使用 `/scan`。",
            ephemeral=True,
        )
        return False

    @bot.tree.command(name="summary", description="顯示目前 FF14 名單摘要。")
    async def summary_command(interaction: discord.Interaction) -> None:
        if not await ensure_target_command_channel(interaction):
            return

        summary = bot.store.write_summary(settings.output_path)
        stats = _summary_stats(summary)
        embed = discord.Embed(
            title="名單摘要",
            color=discord.Color.blurple(),
            description=(
                f"玩家總數：{stats['total_players']}\n"
                f"總紀錄數：{stats['total_records']}\n"
                f"未解析紀錄：{stats['unparsed_records']}"
            ),
        )
        embed.add_field(
            name="評價分布",
            value=(
                f"{GOOD_MARKER} 被讚好玩家：{stats['good_players']}\n"
                f"{BAD_MARKER} 被標記糟糕玩家：{stats['bad_players']}\n"
                f"正負評都有：{stats['mixed_players']}"
            ),
            inline=False,
        )
        embed.add_field(
            name="資料品質",
            value=f"尚未確認世界的玩家：{stats['needs_world_review_players']}",
            inline=False,
        )
        if stats["world_counts"]:
            embed.add_field(name="世界分布", value=stats["world_counts"], inline=False)
        if stats["top_bad_players"]:
            embed.add_field(
                name="累計負評較多",
                value=stats["top_bad_players"],
                inline=False,
            )
        if stats["top_good_players"]:
            embed.add_field(
                name="累計好評較多",
                value=stats["top_good_players"],
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(name="unparsed", description="顯示最近無法解析的評價訊息。")
    async def unparsed_command(interaction: discord.Interaction) -> None:
        if not await ensure_target_command_channel(interaction):
            return

        summary = bot.store.write_summary(settings.output_path)
        records = summary["unparsed"][-5:]
        if not records:
            await interaction.response.send_message("目前沒有未解析紀錄。", ephemeral=True)
            return

        lines = [
            f"- `{record['reason']}` {_short_timestamp(record.get('timestamp'))}：{record['text']}"
            for record in records
        ]
        await interaction.response.send_message(
            "最近未解析紀錄：\n" + "\n".join(lines),
            ephemeral=True,
        )

    @bot.tree.command(name="recent", description="顯示近期加入的名單紀錄。")
    @app_commands.describe(
        rating="依照評價篩選。",
        page="頁碼，從 1 開始。",
        page_size="每頁筆數，最多 20 筆。",
    )
    @app_commands.choices(
        rating=[
            app_commands.Choice(name="✅ 讚好", value="good"),
            app_commands.Choice(name="❌ 糟糕", value="bad"),
        ]
    )
    async def recent_command(
        interaction: discord.Interaction,
        rating: str | None = None,
        page: int = 1,
        page_size: int = 8,
    ) -> None:
        if not await ensure_target_command_channel(interaction):
            return

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
            embed=view.embed(),
            view=view if view.total_pages > 1 else None,
            ephemeral=True,
        )

    @bot.tree.command(name="scan", description="掃描目前頻道歷史訊息並重建名單。")
    @app_commands.describe(limit="最多掃描最近幾則訊息；留空表示全部掃描。")
    async def scan_command(interaction: discord.Interaction, limit: int | None = None) -> None:
        if not await ensure_target_command_channel(interaction):
            return
        if not await ensure_scan_user(interaction):
            return

        if limit is not None and limit < 1:
            await interaction.response.send_message("掃描數量至少要是 1。", ephemeral=True)
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
                f"掃描完成。\n"
                f"掃描訊息：{scanned}\n"
                f"收錄評價訊息：{len(messages)}\n"
                f"玩家總數：{len(summary['players'])}\n"
                f"未解析紀錄：{summary['source']['unparsed_records']}"
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
        for line in record_content_lines(content)
    )


def _is_reaction_role_payload(payload: Any, settings: BotSettings) -> bool:
    return (
        bool(settings.reaction_role_map)
        and payload.channel_id == settings.reaction_role_channel_id
        and payload.message_id == settings.reaction_role_message_id
    )


def _reaction_role_map_from_env(value: str | None) -> dict[str, int]:
    if not value:
        return {}

    try:
        raw_map = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "DISCORD_REACTION_ROLE_MAP must be a JSON object, "
            'for example {"🌬️":123456789012345678}'
        ) from exc

    if not isinstance(raw_map, dict):
        raise ValueError("DISCORD_REACTION_ROLE_MAP must be a JSON object")

    role_map: dict[str, int] = {}
    for emoji, role_id in raw_map.items():
        if not isinstance(emoji, str) or not emoji.strip():
            raise ValueError("DISCORD_REACTION_ROLE_MAP keys must be emoji strings")

        emoji_key = _reaction_role_emoji_key(emoji)
        if emoji_key in role_map:
            raise ValueError(f"DISCORD_REACTION_ROLE_MAP contains duplicate emoji: {emoji}")

        try:
            role_map[emoji_key] = int(role_id)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "DISCORD_REACTION_ROLE_MAP values must be Discord role IDs"
            ) from exc

    return role_map


def _validate_reaction_role_settings(
    *,
    channel_id: int | None,
    message_id: int | None,
    role_map: dict[str, int],
) -> None:
    if channel_id is None and message_id is None and not role_map:
        return

    missing: list[str] = []
    if channel_id is None:
        missing.append("DISCORD_REACTION_ROLE_CHANNEL_ID")
    if message_id is None:
        missing.append("DISCORD_REACTION_ROLE_MESSAGE_ID")
    if not role_map:
        missing.append("DISCORD_REACTION_ROLE_MAP")

    if missing:
        raise ValueError(
            ", ".join(missing)
            + " must be set together to enable reaction roles"
        )


def _reaction_role_emoji_key(value: Any) -> str:
    return str(value).strip().replace("\ufe0f", "")


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
                    "count": player.get("count"),
                    "good_count": player.get("good_count"),
                    "bad_count": player.get("bad_count"),
                    "score": player.get("score"),
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
    label = _rating_label(rating)

    if total == 0:
        return f"目前沒有 `{label}` 的近期紀錄。"

    start = (page - 1) * page_size
    current_records = records[start : start + page_size]
    lines = [f"近期名單 `{label}` 第 {page}/{total_pages} 頁，共 {total} 筆"]

    for offset, record in enumerate(current_records, start=start + 1):
        marker = _rating_marker(record.get("rating"))
        key = record.get("key") or record.get("name") or "未知玩家"
        details = _format_recent_record_details(record, reason_length=100).replace("\n", "｜")
        lines.append(f"{offset}. {marker} `{key}`｜{details}")

    return "\n".join(lines)


def _format_recent_record_details(record: dict[str, Any], *, reason_length: int) -> str:
    author = record.get("author") or "未知加入者"
    timestamp = _short_timestamp(record.get("timestamp"))
    lines = [
        f"加入者：{author}",
        f"時間：{timestamp}",
        f"累計：{_rating_counts_label(record)}",
    ]
    reason = _display_reason(record.get("reason"))
    if reason:
        lines.append(f"理由：{_truncate(reason, reason_length)}")
    return "\n".join(lines)


def _rating_counts_label(record: dict[str, Any]) -> str:
    good_count = _int_value(record.get("good_count"))
    bad_count = _int_value(record.get("bad_count"))
    count = _int_value(record.get("count"), default=good_count + bad_count)
    score = _int_value(record.get("score"), default=good_count - bad_count)
    return f"{GOOD_MARKER} {good_count} / {BAD_MARKER} {bad_count}（共 {count}，分數 {score:+d}）"


def _display_reason(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _clamp_page(page: int, total_records: int, page_size: int) -> int:
    return min(max(1, page), _total_pages(total_records, page_size))


def _clamp_page_size(page_size: int) -> int:
    return min(20, max(1, page_size))


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
        return f"{GOOD_MARKER} 讚好"
    if rating == "bad":
        return f"{BAD_MARKER} 糟糕"
    return "全部"


def _rating_color(rating: str | None) -> int:
    if rating == "good":
        return 0x57F287
    if rating == "bad":
        return 0xED4245
    return 0x5865F2


def _summary_stats(summary: dict[str, Any]) -> dict[str, Any]:
    players = summary.get("players", [])
    source = summary.get("source", {})
    good_players = 0
    bad_players = 0
    mixed_players = 0
    needs_world_review_players = 0

    for player in players:
        has_good = int(player.get("good_count") or 0) > 0
        has_bad = int(player.get("bad_count") or 0) > 0
        if has_good:
            good_players += 1
        if has_bad:
            bad_players += 1
        if has_good and has_bad:
            mixed_players += 1
        if player.get("needs_world_review"):
            needs_world_review_players += 1

    return {
        "total_players": len(players),
        "total_records": source.get("parsed_records", 0),
        "unparsed_records": source.get("unparsed_records", 0),
        "good_players": good_players,
        "bad_players": bad_players,
        "mixed_players": mixed_players,
        "needs_world_review_players": needs_world_review_players,
        "world_counts": _format_world_counts(summary.get("world_counts", [])),
        "top_bad_players": _format_top_players(players, rating="bad"),
        "top_good_players": _format_top_players(players, rating="good"),
    }


def _format_top_players(
    players: list[dict[str, Any]],
    *,
    rating: str,
    limit: int = 5,
) -> str:
    count_key = "bad_count" if rating == "bad" else "good_count"
    ranked = sorted(
        (player for player in players if _int_value(player.get(count_key)) > 0),
        key=lambda player: (
            _int_value(player.get(count_key)),
            _int_value(player.get("count")),
            str(player.get("last_seen") or ""),
        ),
        reverse=True,
    )
    if not ranked:
        return ""

    lines: list[str] = []
    for index, player in enumerate(ranked[:limit], start=1):
        key = player.get("key") or player.get("name") or "未知玩家"
        lines.append(
            f"{index}. {key}："
            f"{GOOD_MARKER} {_int_value(player.get('good_count'))} / "
            f"{BAD_MARKER} {_int_value(player.get('bad_count'))}"
            f"（分數 {_int_value(player.get('score')):+d}）"
        )
    return "\n".join(lines)


def _format_world_counts(world_counts: list[dict[str, Any]]) -> str:
    if not world_counts:
        return ""

    parts: list[str] = []
    for record in world_counts:
        world = record.get("world") or "未記錄"
        parts.append(f"{world}：{record.get('count', 0)}")
    return "、".join(parts)


def _short_timestamp(timestamp: Any) -> str:
    if not timestamp:
        return "未知時間"
    value = str(timestamp)
    return value.replace("T", " ")[:16]


def _truncate(value: str, length: int) -> str:
    if len(value) <= length:
        return value
    return value[: length - 3].rstrip() + "..."


def _int_value(value: Any, *, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


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
