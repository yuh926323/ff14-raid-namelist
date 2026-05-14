from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ff14_raid_namelist.store import NamelistStore


def record(
    message_id: str,
    content: str,
    *,
    timestamp: str = "2026-05-14T10:00:00+00:00",
) -> dict:
    return {
        "id": message_id,
        "timestamp": timestamp,
        "content": content,
        "author": {"name": "note-taker"},
    }


class NamelistStoreTests(unittest.TestCase):
    def test_new_store_starts_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = NamelistStore.load(Path(temp_dir) / "bot-data.json")

            self.assertEqual(store.messages, [])
            self.assertIsNone(store.channel_id)

    def test_upsert_replaces_existing_message_and_writes_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "bot-data.json"
            output_path = Path(temp_dir) / "namelist.json"
            store = NamelistStore.load(store_path)

            store.upsert_message(record("1", "✅ Alpha Beta@Tonberry"))
            store.upsert_message(record("1", "❌ Alpha Beta@Tonberry"))
            store.save()
            summary = store.write_summary(output_path)

            self.assertEqual(len(store.messages), 1)
            self.assertEqual(summary["players"][0]["good_count"], 0)
            self.assertEqual(summary["players"][0]["bad_count"], 1)
            self.assertTrue(store_path.exists())
            self.assertTrue(output_path.exists())

    def test_replace_messages_sorts_and_persists_channel_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "bot-data.json"
            store = NamelistStore.load(store_path)

            store.replace_messages(
                [
                    record("2", "❌ Gamma Delta", timestamp="2026-05-14T11:00:00+00:00"),
                    record("1", "✅ Alpha Beta", timestamp="2026-05-14T10:00:00+00:00"),
                ],
                channel_id=123,
            )
            store.save()

            persisted = json.loads(store_path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["channel_id"], "123")
            self.assertEqual([message["id"] for message in persisted["messages"]], ["1", "2"])

    def test_remove_message_returns_whether_anything_changed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = NamelistStore.load(Path(temp_dir) / "bot-data.json")
            store.upsert_message(record("1", "✅ Alpha Beta"))

            self.assertTrue(store.remove_message("1"))
            self.assertFalse(store.remove_message("1"))
            self.assertEqual(store.messages, [])


if __name__ == "__main__":
    unittest.main()
