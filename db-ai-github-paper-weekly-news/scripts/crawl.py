#!/usr/bin/env python3
"""
db-ai-github-paper-weekly-news crawler orchestrator.

Per-source fetch with status enum, time-window filter, and structured output.
Designed to be invoked by Claude via Skill, but also runnable standalone:

    python3 scripts/crawl.py --output /tmp/crawl_result.json

When run standalone it uses `requests` + `beautifulsoup4` if available; on any
HTTP error it falls back to writing a stub JSON with status="error" so the
report rendering step still produces a "data source coverage" table.

The primary execution path is via Claude using WebFetch / WebSearch (per
CLAUDE.md: must use mcp__MiniMax__web_search for web search). The JSON
schema in `SourceResult` here is the contract between this skill's
crawl phase and its render phase.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Iterable

# --- data structures ----------------------------------------------------------


@dataclass
class Item:
    date: str            # YYYY-MM-DD
    title: str
    url: str
    summary: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass
class SourceResult:
    source_id: int
    category: str        # PG | DB | AI | GH | Paper
    name: str
    base_url: str
    resolved_url: str = ""        # after dynamic resolution (e.g. postgresweekly /issues/N)
    status: str = "pending"       # ok | empty | error | human_required
    status_detail: str = ""
    items: list[Item] = field(default_factory=list)


# --- source registry ----------------------------------------------------------

SOURCES: list[dict[str, Any]] = [
    {
        "source_id": 1, "category": "PG", "name": "postgresweekly.com",
        "base_url": "https://postgresweekly.com/issues",
        "dynamic": True,
    },
    {
        "source_id": 2, "category": "PG", "name": "planet.postgresql.org",
        "base_url": "https://planet.postgresql.org/",
        "dynamic": False,
    },
    {
        "source_id": 3, "category": "PG", "name": "planet.postgis.net",
        "base_url": "https://planet.postgis.net/",
        "dynamic": False,
    },
    {
        "source_id": 4, "category": "PG", "name": "postgresql.org/about/newsarchive",
        "base_url": "https://www.postgresql.org/about/newsarchive/",
        "dynamic": False,
    },
    {
        "source_id": 5, "category": "PG", "name": "git.postgresql.org shortlog",
        "base_url": "https://git.postgresql.org/gitweb/?p=postgresql.git;a=shortlog",
        "dynamic": False,
        "human_required_likely": True,
    },
    {
        "source_id": 6, "category": "DB", "name": "duckdb.org/news",
        "base_url": "https://duckdb.org/news/",
        "dynamic": False,
    },
    {
        "source_id": 7, "category": "AI", "name": "aibase.com/zh",
        "base_url": "https://www.aibase.com/zh",
        "dynamic": False,
    },
    {
        "source_id": 8, "category": "AI", "name": "ai-bot.cn/daily-ai-news",
        "base_url": "https://ai-bot.cn/daily-ai-news/",
        "dynamic": False,
    },
    {
        "source_id": 9, "category": "GH", "name": "github.com/trending?since=weekly",
        "base_url": "https://github.com/trending?since=weekly&spoken_language_code=",
        "dynamic": False,
    },
    {
        "source_id": 10, "category": "Paper", "name": "huggingface.co/papers/trending",
        "base_url": "https://huggingface.co/papers/trending",
        "dynamic": False,
    },
]


# --- time-window filter -------------------------------------------------------


def within_window(item_date: str, today: date, days: int = 7) -> bool:
    """True iff item_date is within [today - days, today]."""
    try:
        d = datetime.strptime(item_date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return False
    return today - timedelta(days=days) <= d <= today


# --- standalone HTTP fetch (best-effort, optional deps) ----------------------


def _http_get(url: str, timeout: int = 10) -> tuple[int, str]:
    """Returns (status_code, body). Uses requests if available, else urllib.

    Never raises — network/timeout/SSL errors return (0, 'FETCH_ERROR: ...').
    """
    try:
        import requests  # type: ignore

        r = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "db-ai-weekly-news/1.0 (+https://example.local)"},
        )
        return r.status_code, r.text
    except ImportError:
        import urllib.request

        req = urllib.request.Request(
            url, headers={"User-Agent": "db-ai-weekly-news/1.0"}
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
                return resp.status, resp.read().decode("utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001
            return 0, f"FETCH_ERROR: {type(e).__name__}: {e}"
    except Exception as e:  # noqa: BLE001
        return 0, f"FETCH_ERROR: {type(e).__name__}: {e}"


def stub_for_source(source: dict[str, Any], status: str, detail: str = "") -> SourceResult:
    return SourceResult(
        source_id=source["source_id"],
        category=source["category"],
        name=source["name"],
        base_url=source["base_url"],
        resolved_url=source["base_url"],
        status=status,
        status_detail=detail,
        items=[],
    )


# --- dynamic URL resolution ---------------------------------------------------


def resolve_postgresweekly_latest(html: str) -> int | None:
    """Find the latest issue number from postgresweekly.com/issues HTML.

    Looks for anchor hrefs of the form /issues/<N> where N is a positive int,
    returns the max N.
    """
    import re

    candidates = re.findall(r"/issues/(\d+)", html)
    if not candidates:
        return None
    return max(int(c) for c in candidates)


# --- main ---------------------------------------------------------------------


def crawl_all(today: date | None = None) -> list[SourceResult]:
    """Standalone crawl. Real execution uses Claude's WebFetch — see SKILL.md."""
    today = today or date.today()
    results: list[SourceResult] = []

    for src in SOURCES:
        url = src["base_url"]
        try:
            status, body = _http_get(url)
        except Exception as e:  # noqa: BLE001
            results.append(stub_for_source(src, "error", f"{type(e).__name__}: {e}"))
            continue

        if status == 0 or status >= 400:
            detail = body if status == 0 else f"HTTP {status}"
            results.append(stub_for_source(src, "error", detail))
            continue

        if src.get("dynamic") and "postgresweekly" in url:
            n = resolve_postgresweekly_latest(body)
            if n is None:
                results.append(stub_for_source(src, "error", "could_not_parse_issue_number"))
                continue
            resolved = f"https://postgresweekly.com/issues/{n}"
            r = stub_for_source(src, "ok", f"resolved_issue={n}")
            r.resolved_url = resolved
            results.append(r)
            continue

        # For all other sources: leave items empty with status="empty".
        # Claude fills items via WebFetch in the main execution path.
        r = stub_for_source(src, "empty", "raw_html_only_no_parser")
        results.append(r)

    return results


def filter_to_window(items: Iterable[Item], today: date, days: int = 7) -> list[Item]:
    return [it for it in items if within_window(it.date, today, days)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="-", help="JSON output path, '-' for stdout")
    args = parser.parse_args()

    results = crawl_all()
    payload = {
        "crawled_at": datetime.now().isoformat(timespec="seconds"),
        "sources": [asdict(r) for r in results],
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output == "-":
        sys.stdout.write(text + "\n")
    else:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"wrote {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())