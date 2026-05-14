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
TW_WORLDS = (
    "伊弗利特",
    "利維坦",
    "巴哈姆特",
    "鳳凰",
    "奧汀",
    "迦樓羅",
    "泰坦",
)

_NAME_PART = r"[A-Z][A-Za-z'-]{1,14}"
_WORLD = r"[A-Za-z][A-Za-z0-9'-]{1,31}"
PLAYER_RE = re.compile(
    rf"(?<![A-Za-z])"
    rf"(?P<name>(?:{_NAME_PART})\s+(?:{_NAME_PART}))"
    rf"(?:\s*(?:[@＠]\s*(?P<world_at>{_WORLD})|\((?P<world_paren>{_WORLD})\)))?"
    rf"(?![A-Za-z])"
)
ENTRY_SPLIT_RE = re.compile(r"\s*[|｜]\s*(?=[✅❌])")
ENTRY_START_RE = re.compile(r"^\s*(?P<marker>[✅❌])\s*(?P<body>.*)$")
TRAILING_WORLD_PAREN_RE = re.compile(r"^[)）\]}】】\s:：,，、-]+")
ENTRY_SEPARATOR_RE = re.compile(r"[\s:：,，、()（）]+")


@dataclass(frozen=True)
class Mention:
    name: str
    world: str | None


@dataclass(frozen=True)
class ParsedMention:
    mention: Mention
    reason: str | None


@dataclass(frozen=True)
class Evidence:
    message_id: str | None
    timestamp: str | None
    author: str | None
    rating: Rating
    text: str
    reason: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "timestamp": self.timestamp,
            "author": self.author,
            "rating": self.rating,
            "text": self.text,
            "reason": self.reason,
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

    @property
    def count(self) -> int:
        return self.good_count + self.bad_count

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
            "count": self.count,
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
            entries = _rating_entries(line)
            if not entries:
                continue

            for entry in entries:
                message_had_rating_line = True

                marker_match = ENTRY_START_RE.match(entry)
                if marker_match is None:
                    continue

                body = marker_match.group("body")
                if GOOD_MARKER in body or BAD_MARKER in body:
                    unparsed.append(
                        _unparsed_record(metadata, "mixed_rating_markers", entry)
                    )
                    continue

                rating: Rating = (
                    "good" if marker_match.group("marker") == GOOD_MARKER else "bad"
                )
                parsed_mentions = extract_parsed_mentions(entry)
                if not parsed_mentions:
                    unparsed.append(_unparsed_record(metadata, "no_player_names", entry))
                    continue

                seen_in_entry: set[tuple[str, str | None]] = set()
                for parsed in parsed_mentions:
                    mention_key = (
                        _identity(parsed.mention.name),
                        _optional_identity(parsed.mention.world),
                    )
                    if mention_key in seen_in_entry:
                        continue

                    seen_in_entry.add(mention_key)
                    events.append(
                        Event(
                            mention=parsed.mention,
                            evidence=Evidence(
                                message_id=metadata["message_id"],
                                timestamp=metadata["timestamp"],
                                author=metadata["author"],
                                rating=rating,
                                text=_trim_text(entry),
                                reason=parsed.reason,
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
        "world_counts": _world_counts(players),
        "players": [player.to_json() for player in players],
        "unparsed": unparsed,
    }


def extract_mentions(text: str) -> list[Mention]:
    return [parsed.mention for parsed in extract_parsed_mentions(text)]


def extract_parsed_mentions(text: str) -> list[ParsedMention]:
    marker_match = ENTRY_START_RE.match(text)
    body = marker_match.group("body") if marker_match else text
    body = _strip_entry_prefix(body)

    latin_mentions = _extract_latin_mentions(body)
    if latin_mentions:
        return latin_mentions

    generic_mention = _extract_single_generic_mention(body)
    return [generic_mention] if generic_mention else []


def _extract_latin_mentions(text: str) -> list[ParsedMention]:
    matches = list(PLAYER_RE.finditer(text))
    if not matches or matches[0].start() != 0:
        return []

    parsed: list[ParsedMention] = []
    for match in matches:
        name = _normalize_display(match.group("name"))
        world = match.group("world_at") or match.group("world_paren")
        reason = None
        if len(matches) == 1:
            reason = _clean_reason(text[match.end() :])
        parsed.append(
            ParsedMention(
                mention=Mention(
                    name=name,
                    world=_normalize_display(world) if world else None,
                ),
                reason=reason,
            )
        )
    return parsed


def _extract_single_generic_mention(text: str) -> ParsedMention | None:
    body = _strip_entry_prefix(text)
    if not body:
        return None

    mention_with_world = _extract_at_world_mention(body)
    if mention_with_world is not None:
        return mention_with_world

    mention_with_world = _extract_parenthesized_world_mention(body)
    if mention_with_world is not None:
        return mention_with_world

    mention_with_world = _extract_tw_separator_world_mention(body)
    if mention_with_world is not None:
        return mention_with_world

    name, reason = _split_name_and_reason_without_world(body)
    if not name:
        return None
    return ParsedMention(mention=Mention(name=name, world=None), reason=reason)


def _extract_at_world_mention(text: str) -> ParsedMention | None:
    match = re.match(r"(?P<name>[^@＠|｜]+?)\s*[@＠]\s*(?P<after>.+)$", text)
    if match is None:
        return None

    name = _clean_name(match.group("name"))
    world, reason = _split_world_and_reason(match.group("after"))
    if not name or world is None:
        return None
    return ParsedMention(mention=Mention(name=name, world=world), reason=reason)


def _extract_parenthesized_world_mention(text: str) -> ParsedMention | None:
    match = re.match(
        r"(?P<name>[^()（）|｜]+?)\s*[（(]\s*(?P<world>[^)）]+)\s*[)）](?P<reason>.*)$",
        text,
    )
    if match is None:
        return None

    world = _clean_world(match.group("world"))
    if world is None:
        return None

    name = _clean_name(match.group("name"))
    if not name:
        return None
    return ParsedMention(
        mention=Mention(name=name, world=world),
        reason=_clean_reason(match.group("reason")),
    )


def _extract_tw_separator_world_mention(text: str) -> ParsedMention | None:
    best_match: tuple[int, str] | None = None
    for world in TW_WORLDS:
        index = text.find(world)
        if index <= 0:
            continue
        previous = text[index - 1]
        if previous not in " \t:：,，、（(":
            continue
        if best_match is None or index < best_match[0]:
            best_match = (index, world)

    if best_match is None:
        return None

    index, world = best_match
    name = _clean_name(text[:index])
    if not name:
        return None

    reason = _clean_reason(text[index + len(world) :])
    return ParsedMention(mention=Mention(name=name, world=world), reason=reason)


def _split_world_and_reason(text: str) -> tuple[str | None, str | None]:
    body = text.strip()
    for world in TW_WORLDS:
        if body.startswith(world):
            return world, _clean_reason(body[len(world) :])

    match = re.match(r"(?P<world>[A-Za-z][A-Za-z0-9'-]{1,31})(?P<reason>.*)$", body)
    if match is None:
        return None, None
    return _normalize_display(match.group("world")), _clean_reason(match.group("reason"))


def _split_name_and_reason_without_world(text: str) -> tuple[str | None, str | None]:
    body = _strip_entry_prefix(text)
    if not body:
        return None, None

    separator_match = ENTRY_SEPARATOR_RE.search(body)
    if separator_match is None:
        return _clean_name(body), None

    name = _clean_name(body[: separator_match.start()])
    reason = _clean_reason(body[separator_match.start() :])
    return name, reason


def _rating_entries(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith((GOOD_MARKER, BAD_MARKER)):
        return []
    return [entry.strip() for entry in ENTRY_SPLIT_RE.split(stripped) if entry.strip()]


def _strip_entry_prefix(text: str) -> str:
    return text.strip().lstrip(":：-—").strip()


def _clean_name(text: str) -> str | None:
    name = _normalize_display(text)
    name = name.strip(" \t:：,，、()（）[]【】")
    return name or None


def _clean_world(text: str) -> str | None:
    world = _normalize_display(text)
    if world in TW_WORLDS:
        return world
    if re.fullmatch(_WORLD, world):
        return world
    return None


def _clean_reason(text: str) -> str | None:
    reason = TRAILING_WORLD_PAREN_RE.sub("", text).strip()
    reason = _normalize_display(reason)
    return reason or None


def _world_counts(players: list[PlayerAccumulator]) -> list[dict[str, Any]]:
    counts: dict[str, dict[str, Any]] = {}
    for player in players:
        world = player.world or "未記錄"
        record = counts.setdefault(
            world,
            {"world": player.world, "needs_world_review": player.world is None, "count": 0},
        )
        record["count"] += player.count

    return sorted(
        counts.values(),
        key=lambda record: (record["world"] is None, str(record["world"])),
    )

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
