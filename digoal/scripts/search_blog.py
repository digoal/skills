#!/usr/bin/env python3
"""Read-only search helper for a digoal/blog checkout."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path


def looks_like_blog_root(path: Path) -> bool:
    return (
        (path / "README.md").is_file()
        and (path / "CLAUDE.md").is_file()
        and (path / "class").is_dir()
    )


def discover_blog_root() -> Path:
    env_root = os.environ.get("DIGOAL_BLOG_ROOT")
    if env_root:
        root = Path(env_root).expanduser().resolve()
        if looks_like_blog_root(root):
            return root
        raise SystemExit(f"DIGOAL_BLOG_ROOT is not a digoal/blog root: {root}")

    starts = [Path.cwd().resolve(), Path(__file__).resolve()]
    for start in starts:
        for candidate in [start, *start.parents]:
            if looks_like_blog_root(candidate):
                return candidate

    home = Path.home()
    common_roots = [
        home / "blog",
        home / "digoal" / "blog",
        home / "workspace" / "blog",
        home / "work" / "blog",
        home / "projects" / "blog",
        home / "src" / "blog",
    ]
    for candidate in common_roots:
        candidate = candidate.expanduser().resolve()
        if looks_like_blog_root(candidate):
            return candidate

    raise SystemExit(
        "Could not locate a local digoal/blog root. Provide one of:\n"
        "  1. Run this command from the blog checkout.\n"
        "  2. Place the skill under blog/skills/digoal.\n"
        "  3. Keep the checkout at ~/blog or set DIGOAL_BLOG_ROOT=/path/to/blog.\n"
        "  4. Pass --blog /path/to/blog.\n"
        "If you are an agent using this skill, ask the user for the local blog folder path before continuing."
    )


def iter_markdown_files(root: Path):
    skip = {".git", "skills"}
    for path in root.rglob("*.md"):
        if any(part in skip for part in path.parts):
            continue
        yield path


def title_for(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                stripped = line.strip()
                if stripped.startswith("#"):
                    return stripped.lstrip("#").strip()
    except OSError:
        pass
    return ""


def search_file(path: Path, pattern: re.Pattern[str], titles_only: bool, max_matches: int):
    title = title_for(path)
    if titles_only:
        if pattern.search(title):
            return [(0, title)]
        return []

    matches = []
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for lineno, line in enumerate(handle, 1):
                if pattern.search(line):
                    matches.append((lineno, line.strip()))
                    if len(matches) >= max_matches:
                        break
    except OSError:
        return []
    return matches


def main() -> int:
    parser = argparse.ArgumentParser(description="Search digoal/blog markdown files without modifying them.")
    parser.add_argument("query", help="Regex or literal query. Use --literal for plain text.")
    parser.add_argument("--blog", help="Blog root path. Defaults to auto-discovery.")
    parser.add_argument("--limit", type=int, default=20, help="Maximum files to print.")
    parser.add_argument("--max-matches", type=int, default=3, help="Maximum matching lines per file.")
    parser.add_argument("--literal", action="store_true", help="Treat query as literal text.")
    parser.add_argument("--case-sensitive", action="store_true", help="Use case-sensitive matching.")
    parser.add_argument("--titles-only", action="store_true", help="Search first markdown heading only.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args()

    root = Path(args.blog).expanduser().resolve() if args.blog else discover_blog_root()
    if not root.exists():
        raise SystemExit(f"Blog root does not exist: {root}")
    if not looks_like_blog_root(root):
        raise SystemExit(f"Path is not a digoal/blog root: {root}")

    query = re.escape(args.query) if args.literal else args.query
    flags = 0 if args.case_sensitive else re.IGNORECASE
    pattern = re.compile(query, flags)

    results = []
    printed = 0
    for path in sorted(iter_markdown_files(root), reverse=True):
        matches = search_file(path, pattern, args.titles_only, max(1, args.max_matches))
        if not matches:
            continue
        rel = path.relative_to(root)
        item = {
            "path": str(rel),
            "title": title_for(path),
            "matches": [
                {"line": lineno, "text": text[:240]}
                for lineno, text in matches
            ],
        }
        if args.json:
            results.append(item)
        else:
            print(f"{rel} :: {item['title']}")
            for match in item["matches"]:
                if match["line"]:
                    print(f"  L{match['line']}: {match['text']}")
        printed += 1
        if printed >= args.limit:
            break

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
