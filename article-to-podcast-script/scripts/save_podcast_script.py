#!/usr/bin/env python3
"""Save a generated podcast script to the current project's markdown directory."""

from __future__ import annotations

import re
import sys
from pathlib import Path


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "article"


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: save_podcast_script.py ARTICLE.md SPEAKER_COUNT < script.txt", file=sys.stderr)
        return 2

    article_path = Path(sys.argv[1]).expanduser()
    try:
        speaker_count = int(sys.argv[2])
    except ValueError:
        print("SPEAKER_COUNT must be an integer from 1 to 4", file=sys.stderr)
        return 2

    if speaker_count < 1 or speaker_count > 4:
        print("SPEAKER_COUNT must be an integer from 1 to 4", file=sys.stderr)
        return 2

    script_text = sys.stdin.read().strip()
    if not script_text:
        print("No script text received on stdin", file=sys.stderr)
        return 2

    markdown_dir = Path.cwd() / "markdown"
    markdown_dir.mkdir(parents=True, exist_ok=True)

    output_name = f"{slugify(article_path.stem)}-podcast-{speaker_count}p.txt"
    output_path = markdown_dir / output_name
    output_path.write_text(script_text + "\n", encoding="utf-8")

    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
