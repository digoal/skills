#!/usr/bin/env python3
"""
git.postgresql.org shortlog 解析（含 human_required 兜底）。

git.postgresql.org 在自动化请求频繁时可能返回 anti-bot 页面（人机验证）。
此脚本提供两层路径：

  1. 直接 fetch shortlog HTML，提取 commit hash + author + subject。
  2. 如果失败，则按 SKILL.md references/human-verification.md 兜底：
     用 WebSearch 搜近 7 天内核心 committer 的提交，再合并。

Python 部分只实现第 1 步的 HTML 解析；第 2 步由 Claude 触发。
"""

from __future__ import annotations

import json
import re
import sys

sys.path.insert(0, __import__("os").path.dirname(__file__))
from crawl import _http_get, Item, SourceResult  # type: ignore  # noqa: E402


SHORTLOG_URL = "https://git.postgresql.org/gitweb/?p=postgresql.git;a=shortlog"

# shortlog 页每个 commit 大致结构（gitweb 模板）：
#   <a class="list" href="...?h=ae39bd23...">ae39bd23</a>
#   <span class="commit-subject"><a ...>Subject text</a></span>
#   <i class="author">Author Name</i>  <span class="datetime">2026-06-16</span>
HASH_RE = re.compile(r'<a\s+class="list"\s+href="[^"]*?h=(?P<hash>[0-9a-f]{6,40})"[^>]*>(?P=hash)</a>', re.IGNORECASE)
SUBJECT_RE = re.compile(
    r'<span\s+class="commit-subject"[^>]*>\s*<a[^>]*>(?P<subject>[^<]+)</a>',
    re.IGNORECASE,
)
AUTHOR_RE = re.compile(r'<i\s+class="author"[^>]*>(?P<author>[^<]+)</i>', re.IGNORECASE)
DATE_RE = re.compile(r'<span\s+class="datetime"[^>]*>(?P<date>\d{4}-\d{2}-\d{2})</span>')


def parse_shortlog(html: str, n_commits: int = 50) -> list[Item]:
    """Walk per-commit blocks. The gitweb template renders commits top-down."""
    items: list[Item] = []

    # crude split: each commit has its own <tr> row, but pulling the whole
    # tbody and matching groups in order is more robust.
    hashes = HASH_RE.findall(html)
    subjects = SUBJECT_RE.findall(html)
    authors = AUTHOR_RE.findall(html)
    dates = DATE_RE.findall(html)

    n = min(len(hashes), len(subjects), len(authors), len(dates), n_commits)
    for i in range(n):
        commit_hash = hashes[i]
        subject = subjects[i].strip()
        author = authors[i].strip()
        d = dates[i]
        url = (
            "https://git.postgresql.org/gitweb/?p=postgresql.git;"
            f"a=commit;h={commit_hash}"
        )
        items.append(
            Item(
                date=d,
                title=subject,
                url=url,
                summary=f"by {author}",
                tags=["PG", "内核"],
            )
        )
    return items


def main() -> int:
    status, body = _http_get(SHORTLOG_URL)
    if status != 200:
        result = SourceResult(
            source_id=5,
            category="PG",
            name="git.postgresql.org shortlog",
            base_url=SHORTLOG_URL,
            resolved_url=SHORTLOG_URL,
            status="human_required",
            status_detail=f"HTTP {status} — anti-bot or transient. Use WebSearch fallback.",
            items=[],
        )
        print(json.dumps(result, default=lambda o: o.__dict__, ensure_ascii=False, indent=2))
        return 1

    items = parse_shortlog(body)
    result = SourceResult(
        source_id=5,
        category="PG",
        name="git.postgresql.org shortlog",
        base_url=SHORTLOG_URL,
        resolved_url=SHORTLOG_URL,
        status="ok" if items else "empty",
        status_detail=f"parsed={len(items)}",
        items=items,
    )
    print(json.dumps(result, default=lambda o: o.__dict__, ensure_ascii=False, indent=2))
    return 0 if items else 1


if __name__ == "__main__":
    sys.exit(main())