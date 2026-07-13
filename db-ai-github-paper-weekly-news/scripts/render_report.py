#!/usr/bin/env python3
"""
Render crawl results into the final markdown weekly report.

Inputs: JSON written by crawl.py (or by Claude's WebFetch pipeline).
Output: markdown file at <cwd>/markdown/db-ai-weekly-YYYY-MM-DD.md

This is a reference implementation. The primary execution path renders
markdown directly in Claude's response; this script exists so the layout
is reproducible and can be unit-tested.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from crawl import SourceResult, within_window  # type: ignore  # noqa: E402


HEADER_TEMPLATE = """# 数据库 / AI / GitHub / 论文 周报 · {today}

> 📅 时间窗口：{start} ~ {today}
> 🔗 数据源：{n_sources} 个（成功 {ok} / 空响应 {empty} / 失败 {err} / 人工验证 {human}）
> 📊 总条目：{total}

"""


SECTION_TEMPLATES = {
    "PG": ("## 二、🐘 PostgreSQL 生态", "PG 内核提交 + 社区博客"),
    "DB": ("## 三、🦆 其他数据库（DuckDB 等）", "DuckDB 官方新闻"),
    "AI": ("## 四、🤖 AI 新闻", "国内 AI 新闻为主（aibase + ai-bot）"),
    "GH": ("## 五、⭐ GitHub 趋势项目（weekly）", "本周 trending 仓库"),
    "Paper": ("## 六、📄 AI 论文（HuggingFace Trending）", "本周 trending 论文"),
}


def render(items_by_category: dict[str, list[SourceResult]], today: str, start: str) -> str:
    parts: list[str] = []

    total_items = sum(len(r.items) for rs in items_by_category.values() for r in rs)
    ok = sum(1 for rs in items_by_category.values() for r in rs if r.status == "ok")
    empty = sum(1 for rs in items_by_category.values() for r in rs if r.status == "empty")
    err = sum(1 for rs in items_by_category.values() for r in rs if r.status == "error")
    human = sum(1 for rs in items_by_category.values() for r in rs if r.status == "human_required")
    n_sources = sum(len(rs) for rs in items_by_category.values())

    parts.append(
        HEADER_TEMPLATE.format(
            today=today,
            start=start,
            n_sources=n_sources,
            ok=ok,
            empty=empty,
            err=err,
            human=human,
            total=total_items,
        )
    )

    # --- 七、数据源覆盖表 ---
    parts.append("## 七、数据源覆盖\n")
    parts.append("| # | 类别 | 源 | 状态 | 抓到条目数 | 备注 |")
    parts.append("|---|---|---|---|---|---|")
    all_results = [r for rs in items_by_category.values() for r in rs]
    for r in sorted(all_results, key=lambda x: x.source_id):
        status_emoji = {
            "ok": "✅",
            "empty": "⚠️",
            "error": "❌",
            "human_required": "🙋",
        }.get(r.status, "❔")
        parts.append(
            f"| {r.source_id} | {r.category} | {r.name} | "
            f"{status_emoji} {r.status} | {len(r.items)} | {r.status_detail} |"
        )
    parts.append("")

    # --- 各分类章节（占位：实际条目由 Claude 撰写） ---
    for cat in ("PG", "DB", "AI", "GH", "Paper"):
        header, desc = SECTION_TEMPLATES[cat]
        parts.append(f"---\n\n{header}\n\n> {desc}\n")
        for r in items_by_category.get(cat, []):
            if not r.items:
                parts.append(
                    f"_（{r.name}: status={r.status}, detail={r.status_detail}）_"
                )
                continue
            parts.append(f"### {r.name}\n")
            parts.append("| 时间 | 标题 | 链接 |")
            parts.append("|---|---|---|")
            for it in r.items:
                parts.append(f"| {it.date} | {it.title} | [link]({it.url}) |")
            parts.append("")

    # --- 文件尾 ---
    parts.append("---\n")
    parts.append(
        f"*本周报由 `db-ai-github-paper-weekly-news` skill 于 "
        f"{datetime.now().strftime('%Y-%m-%d %H:%M')} 自动生成。"
        "条目均附原始来源链接，请以原文为准。*\n"
    )
    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="JSON from crawl.py")
    parser.add_argument("--output-dir", default="markdown", help="Output directory")
    parser.add_argument("--today", default=None, help="Override YYYY-MM-DD")
    args = parser.parse_args()

    with open(args.input, encoding="utf-8") as f:
        data = json.load(f)

    today = args.today or datetime.now().date().isoformat()
    start = (datetime.strptime(today, "%Y-%m-%d").date() - timedelta(days=7)).isoformat()

    results = [SourceResult(**r) for r in data["sources"]]
    by_cat: dict[str, list[SourceResult]] = {}
    for r in results:
        by_cat.setdefault(r.category, []).append(r)

    md = render(by_cat, today, start)

    os.makedirs(args.output_dir, exist_ok=True)
    out_path = os.path.join(args.output_dir, f"db-ai-weekly-{today}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())