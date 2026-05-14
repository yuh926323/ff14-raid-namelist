from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .parser import summarize_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ff14-raid-namelist",
        description="Summarize FF14 player notes from DiscordChatExporter JSON.",
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Path to a DiscordChatExporter JSON file.",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Path to write the summarized JSON.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON with indentation.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        summary = summarize_file(args.input)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8") as output:
            json.dump(
                summary,
                output,
                ensure_ascii=False,
                indent=2 if args.pretty else None,
            )
            output.write("\n")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    return 0
