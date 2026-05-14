from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

Rating = Literal["good", "bad"]

GOOD_MARKER = "✅"
BAD_MARKER = "❌"
MAX_EVIDENCE_TEXT_LENGTH = 500

_NAME_PART = r"[A-Z][A-Za-z'-]{1,14}"
_WORLD = r"[A-Za-z][A-Za-z0-9'-]{1,31}"
PLAYER_RE = re.compile(
    rf"(?<![A-Za-z])"
    rf"(?P<name>(?:{_NAME_PART})\s+(?:{_NAME_PART}))"
    rf"(?:\s*(?:[@＠]\s*(?P<world_at>{_WORLD})|\((?P<world_paren>{_WORLD})\)))?"
    rf"(?![A-Za-z])"
)


@dataclass(frozen=True)
class Mention:
    name: str
    world: str | None


@dataclass(frozen=True)
class Evidence:
    message_id: str | None
    timestamp: str | None
    author: str | None
    rating: Rating
    text: str

    def to_json(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "timestamp": self.timestamp,
            "author": self.author,
            "rating": self.rating,
            "text": self.text,
        }


@dataclass(frozen=True)
class Event:
    mention: Mention
    evidence: Evidence


@dataclass
class PlayerAccumulator:
    name: str
    world: str | None
    needs_world_review: bool = False
    good_count: int = 0
    bad_count: int = 0
    last_seen: str | None = None
    evidence: list[Evidence] = field(default_factory=list)

    @property
    def key(self) -> str:
        if self.world:
            return f"{self.name}@{self.world}"
        return self.name

    @property
    def score(self) -> int:
        return self.good_count - self.bad_count

    def add(self, event: Event, *, missing_world: bool) -> None:
        if event.evidence.rating == "good":
            self.good_count += 1
        else:
            self.bad_count += 1

        self.needs_world_review = self.needs_world_review or missing_world
        if self.world is None:
            self.needs_world_review = True

        if _is_later_timestamp(event.evidence.timestamp, self.last_seen):
            self.last_seen = event.evidence.timestamp

        self.evidence.append(event.evidence)

    def to_json(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "world": self.world,
            "needs_world_review": self.needs_world_review,
            "good_count": self.good_count,
            "bad_count": self.bad_count,
            "score": self.score,
            "last_seen": self.last_seen,
            "evidence": [evidence.to_json() for evidence in self.evidence],
        }


def summarize_file(input_path: Path | str) -> dict[str, Any]:
    path = Path(input_path)
    with path.open("r", encoding="utf-8") as input_file:
        data = json.load(input_file)
    return summarize_export(data, input_path=str(path))


def summarize_export(
    data: Any,
    *,
    input_path: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    messages = _extract_messages(data)
    events: list[Event] = []
    unparsed: list[dict[str, Any]] = []
    parsed_message_ids: set[str] = set()
    skipped_messages = 0

    for index, message in enumerate(messages):
        content = _message_content(message)
        message_key = _message_identity(message, index)

        if GOOD_MARKER not in content and BAD_MARKER not in content:
            skipped_messages += 1
            continue

        message_had_event = False
        message_had_rating_line = False
        metadata = _message_metadata(message)

        for line in _content_lines(content):
            has_good = GOOD_MARKER in line
            has_bad = BAD_MARKER in line
            if not has_good and not has_bad:
                continue

            message_had_rating_line = True

            if has_good and has_bad:
                unparsed.append(
                    _unparsed_record(metadata, "mixed_rating_markers", line)
                )
                continue

            rating: Rating = "good" if has_good else "bad"
            mentions = extract_mentions(line)
            if not mentions:
                unparsed.append(_unparsed_record(metadata, "no_player_names", line))
                continue

            seen_in_line: set[tuple[str, str | None]] = set()
            for mention in mentions:
                mention_key = (_identity(mention.name), _optional_identity(mention.world))
                if mention_key in seen_in_line:
                    continue

                seen_in_line.add(mention_key)
                events.append(
                    Event(
                        mention=mention,
                        evidence=Evidence(
                            message_id=metadata["message_id"],
                            timestamp=metadata["timestamp"],
                            author=metadata["author"],
                            rating=rating,
                            text=_trim_text(line),
                        ),
                    )
                )
                message_had_event = True

        if message_had_event:
            parsed_message_ids.add(message_key)
        elif not message_had_rating_line:
            skipped_messages += 1

    players = _aggregate_events(events)

    return {
        "generated_at": generated_at or _utc_now(),
        "source": {
            "input_path": input_path,
            "total_messages": len(messages),
            "parsed_messages": len(parsed_message_ids),
            "parsed_records": len(events),
            "skipped_messages": skipped_messages,
            "unparsed_records": len(unparsed),
        },
        "players": [player.to_json() for player in players],
        "unparsed": unparsed,
    }


def extract_mentions(text: str) -> list[Mention]:
    mentions: list[Mention] = []
    for match in PLAYER_RE.finditer(text):
        name = _normalize_display(match.group("name"))
        world = match.group("world_at") or match.group("world_paren")
        mentions.append(Mention(name=name, world=_normalize_display(world) if world else None))
    return mentions


def _extract_messages(data: Any) -> list[Any]:
    if isinstance(data, dict):
        messages = data.get("messages")
    elif isinstance(data, list):
        messages = data
    else:
        messages = None

    if not isinstance(messages, list):
        raise ValueError("input JSON must be a DiscordChatExporter object with messages[]")

    return messages


def _message_content(message: Any) -> str:
    if not isinstance(message, dict):
        return ""
    content = message.get("content", "")
    if content is None:
        return ""
    return str(content)


def _message_metadata(message: Any) -> dict[str, str | None]:
    if not isinstance(message, dict):
        return {"message_id": None, "timestamp": None, "author": None}

    return {
        "message_id": _optional_string(message.get("id")),
        "timestamp": _optional_string(message.get("timestamp")),
        "author": _author_name(message.get("author")),
    }


def _message_identity(message: Any, index: int) -> str:
    if isinstance(message, dict) and message.get("id") is not None:
        return str(message["id"])
    return f"index:{index}"


def _author_name(author: Any) -> str | None:
    if isinstance(author, dict):
        for key in ("nickname", "name", "username", "id"):
            value = author.get(key)
            if value:
                return str(value)
        return None
    return _optional_string(author)


def _content_lines(content: str) -> list[str]:
    return [line.strip() for line in content.splitlines() if line.strip()]


def _unparsed_record(
    metadata: dict[str, str | None],
    reason: str,
    text: str,
) -> dict[str, Any]:
    return {
        "message_id": metadata["message_id"],
        "timestamp": metadata["timestamp"],
        "author": metadata["author"],
        "reason": reason,
        "text": _trim_text(text),
    }


def _aggregate_events(events: list[Event]) -> list[PlayerAccumulator]:
    known_worlds_by_name: dict[str, set[str]] = {}
    display_names: dict[str, str] = {}
    display_worlds: dict[str, str] = {}

    for event in events:
        name_id = _identity(event.mention.name)
        display_names.setdefault(name_id, event.mention.name)
        if event.mention.world:
            world_id = _identity(event.mention.world)
            known_worlds_by_name.setdefault(name_id, set()).add(world_id)
            display_worlds.setdefault(world_id, event.mention.world)

    players_by_key: dict[tuple[str, str | None], PlayerAccumulator] = {}

    for event in events:
        name_id = _identity(event.mention.name)
        world_id = _optional_identity(event.mention.world)
        missing_world = world_id is None

        if world_id is None:
            known_worlds = known_worlds_by_name.get(name_id, set())
            if len(known_worlds) == 1:
                world_id = next(iter(known_worlds))

        group_key = (name_id, world_id)
        if group_key not in players_by_key:
            players_by_key[group_key] = PlayerAccumulator(
                name=display_names.get(name_id, event.mention.name),
                world=display_worlds.get(world_id) if world_id else None,
            )

        players_by_key[group_key].add(event, missing_world=missing_world)

    return sorted(players_by_key.values(), key=lambda player: player.key.casefold())


def _normalize_display(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def _identity(value: str) -> str:
    return _normalize_display(value).casefold()


def _optional_identity(value: str | None) -> str | None:
    return _identity(value) if value else None


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _trim_text(text: str) -> str:
    normalized = _normalize_display(text)
    if len(normalized) <= MAX_EVIDENCE_TEXT_LENGTH:
        return normalized
    return normalized[: MAX_EVIDENCE_TEXT_LENGTH - 3].rstrip() + "..."


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _is_later_timestamp(candidate: str | None, current: str | None) -> bool:
    if candidate is None:
        return current is None
    if current is None:
        return True

    candidate_dt = _parse_timestamp(candidate)
    current_dt = _parse_timestamp(current)
    if candidate_dt is not None and current_dt is not None:
        return candidate_dt > current_dt

    return candidate > current


def _parse_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
