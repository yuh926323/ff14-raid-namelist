from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .parser import summarize_export

SCHEMA_VERSION = 1


@dataclass
class NamelistStore:
    path: Path
    channel_id: str | None = None
    messages: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path | str) -> "NamelistStore":
        store_path = Path(path)
        if not store_path.exists():
            return cls(path=store_path)

        with store_path.open("r", encoding="utf-8") as input_file:
            data = json.load(input_file)

        if not isinstance(data, dict):
            raise ValueError("store JSON must be an object")
        if data.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(f"unsupported store schema_version: {data.get('schema_version')}")

        messages = data.get("messages", [])
        if not isinstance(messages, list):
            raise ValueError("store messages must be a list")

        return cls(
            path=store_path,
            channel_id=_optional_string(data.get("channel_id")),
            messages=[message for message in messages if isinstance(message, dict)],
        )

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as output_file:
            json.dump(self.to_json(), output_file, ensure_ascii=False, indent=2)
            output_file.write("\n")

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "channel_id": self.channel_id,
            "messages": self.messages,
        }

    def replace_messages(
        self,
        messages: list[dict[str, Any]],
        *,
        channel_id: str | int | None,
    ) -> None:
        self.channel_id = _optional_string(channel_id)
        self.messages = sorted(
            [_normalize_message(message) for message in messages],
            key=_message_sort_key,
        )

    def upsert_message(self, message: dict[str, Any]) -> None:
        normalized = _normalize_message(message)
        message_id = normalized.get("id")
        if message_id is None:
            raise ValueError("message record must include id")

        self.messages = [
            existing for existing in self.messages if existing.get("id") != message_id
        ]
        self.messages.append(normalized)
        self.messages.sort(key=_message_sort_key)

    def remove_message(self, message_id: str | int) -> bool:
        target_id = str(message_id)
        previous_count = len(self.messages)
        self.messages = [
            message for message in self.messages if _optional_string(message.get("id")) != target_id
        ]
        return len(self.messages) != previous_count

    def summarize(self, *, generated_at: str | None = None) -> dict[str, Any]:
        return summarize_export(
            {"messages": self.messages},
            input_path=str(self.path),
            generated_at=generated_at,
        )

    def write_summary(self, output_path: Path | str) -> dict[str, Any]:
        summary = self.summarize()
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as output_file:
            json.dump(summary, output_file, ensure_ascii=False, indent=2)
            output_file.write("\n")
        return summary


def _normalize_message(message: dict[str, Any]) -> dict[str, Any]:
    author = message.get("author")
    if isinstance(author, dict):
        author_record = {
            key: _optional_string(author.get(key))
            for key in ("id", "name", "username", "nickname")
            if author.get(key) is not None
        }
    else:
        author_record = {"name": _optional_string(author)}

    return {
        "id": _optional_string(message.get("id")),
        "timestamp": _optional_string(message.get("timestamp")),
        "content": _optional_string(message.get("content")) or "",
        "author": author_record,
    }


def _message_sort_key(message: dict[str, Any]) -> tuple[str, str]:
    return (
        _optional_string(message.get("timestamp")) or "",
        _optional_string(message.get("id")) or "",
    )


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
