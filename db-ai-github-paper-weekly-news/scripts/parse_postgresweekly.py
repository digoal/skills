#!/usr/bin/env python3
"""
postgresweekly.com 专用解析：先抓 /issues 找到最新 issue N，再抓 /issues/<N>。

为什么单独文件：postgresweekly 侧栏通常按 issue 编号降序列出（/issues/652,
/issues/651, ...），需要在 HTML 里找最大数字。其他源没有这个动态编号步骤。

主执行路径下 Claude 用 WebFetch 调两次；本脚本提供 standalone 实现，
便于 CI / 手动排错时直接复现。
"""

from __future__ import annotations

import json
import re
import sys
from typing import Optional

# 复用 crawl.py 的 HTTP 工具
sys.path.insert(0, __import__("os").path.dirname(__file__))
from crawl import _http_get, Item, SourceResult  # type: ignore  # noqa: E402


LATEST_RE = re.compile(r"/issues/(\d+)")
ITEM_RE = re.compile(
    r'<a[^>]+href="(?P<url>[^"]+)"[^>]*>(?P<title>[^<]+)</a>',
    re.IGNORECASE,
)


def find_latest_issue(html: str) -> Optional[int]:
    nums = [int(n) for n in LATEST_RE.findall(html)]
    return max(nums) if nums else None


def parse_issue_page(html: str, issue_n: int) -> list[Item]:
    """Best-effort extract. Real parsing happens via Claude + WebFetch."""
    out: list[Item] = []
    for m in ITEM_RE.finditer(html):
        url = m.group("url")
        title = m.group("title").strip()
        if not title or "/issues/" in url and url != f"/issues/{issue_n}":
            continue
        out.append(
            Item(
                date="",  # WebFetch 阶段由 Claude 按上下文补
                title=title,
                url=f"https://postgresweekly.com{url}" if url.startswith("/") else url,
                summary="",
                tags=["PG", "weekly"],
            )
        )
    return out


def main() -> int:
    base = "https://postgresweekly.com/issues"
    status, body = _http_get(base)
    if status != 200:
        print(json.dumps({"status": "error", "http": status}, ensure_ascii=False))
        return 1

    n = find_latest_issue(body)
    if n is None:
        print(json.dumps({"status": "error", "detail": "no_issue_number_found"}))
        return 1

    status2, body2 = _http_get(f"{base}/{n}")
    if status2 != 200:
        print(
            json.dumps(
                {"status": "error", "issue": n, "http": status2},
                ensure_ascii=False,
            )
        )
        return 1

    items = parse_issue_page(body2, n)
    result = SourceResult(
        source_id=1,
        category="PG",
        name="postgresweekly.com",
        base_url=base,
        resolved_url=f"{base}/{n}",
        status="ok" if items else "empty",
        status_detail=f"issue={n}",
        items=items,
    )
    print(json.dumps(result, default=lambda o: o.__dict__, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())