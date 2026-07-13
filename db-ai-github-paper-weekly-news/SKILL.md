---
name: db-ai-github-paper-weekly-news
description: 抓取并汇总"数据库、AI、GitHub、AI 论文"近 1 周新闻，输出图文并茂（含 mermaid 图）的 markdown 周报到当前项目的 markdown/ 目录。覆盖 10 个数据源：postgresweekly.com/issues（自动解析最新 issue 编号）、planet.postgresql.org、planet.postgis.net、postgresql.org/about/newsarchive/、git.postgresql.org shortlog、duckdb.org/news/、aibase.com/zh、ai-bot.cn/daily-ai-news、github.com/trending?since=weekly、huggingface.co/papers/trending。适用于：用户提出"生成周报"、"本周数据库+AI+GitHub+论文快讯"、"跑一次 db-ai-weekly"、"weekly news"等需求。
---

# DB+AI+GitHub+Paper 周报

## 概述

从 10 个数据源抓取最近 7 天内容，按"PostgreSQL 生态 / 其他数据库 / AI 新闻 / GitHub 趋势 / AI 论文"5 大类汇总，生成含 mermaid 图表的 markdown 周报，写入当前项目 `markdown/` 目录（默认文件名 `db-ai-weekly-YYYY-MM-DD.md`，日期为执行当天）。

## 数据源清单

| # | 类别 | URL | 抓取策略 |
|---|---|---|---|
| 1 | PG 周报 | `https://postgresweekly.com/issues` | **动态**：先抓 `/issues` 解析最新 issue 编号（如 `652`），再抓 `/issues/<N>` |
| 2 | PG 社区 | `https://planet.postgresql.org/` | RSS / 列表页 |
| 3 | PostGIS | `https://planet.postgis.net/` | RSS / 列表页 |
| 4 | PG 官方 | `https://www.postgresql.org/about/newsarchive/` | 列表页 |
| 5 | PG 内核 | `https://git.postgresql.org/gitweb/?p=postgresql.git;a=shortlog` | shortlog HTML（**可能需要人工验证**，详见 `references/human-verification.md`） |
| 6 | DuckDB | `https://duckdb.org/news/` | 列表页 |
| 7 | AI 国内 | `https://www.aibase.com/zh` | 列表页 + 文章页 |
| 8 | AI 国内 | `https://ai-bot.cn/daily-ai-news/` | 列表页 |
| 9 | GitHub | `https://github.com/trending?since=weekly&spoken_language_code=` | 列表页 |
| 10 | 论文 | `https://huggingface.co/papers/trending` | 列表页 |

## 工作流（执行步骤）

按以下顺序执行；任一步失败不阻塞整体，错误归入"数据源覆盖"章节的失败表。

### Step 1. 解析动态 URL

- 对 `postgresweekly.com/issues`：用 `mcp__MiniMax__web_search` 或 `WebFetch` 抓 `/issues`，从侧栏/列表中识别最新 issue 编号 N（纯数字），构造 `https://postgresweekly.com/issues/<N>` 作为实际抓取入口。
- 其他源直接用表中 URL。

### Step 2. 并行抓取（每个源独立调用 WebFetch / WebSearch）

使用 `mcp__MiniMax__web_search`（根据 `CLAUDE.md` 规则）或 `WebFetch`。每个源返回结构化字段：

```
{
  source_id: 1..10,
  url: 实际抓取 URL,
  status: "ok" | "empty" | "error" | "human_required",
  status_detail: "529" / "NO_RECENT_ITEMS" / ...,
  items: [
    {
      date: "2026-06-16",
      title: "...",
      url: "...",
      summary: "一句话摘要",
      tags: ["PG", "内核", "逻辑复制"]   // 用于分类
    }
  ]
}
```

判定"近 1 周"用 `date >= today - 7 days`，按数据源给出的发布时间为准；无法解析日期的退回到抓取当日。

### Step 3. 失败 / 人工验证处理

- HTTP 5xx、429、超时 → `status="error"`，在周报"数据源覆盖"章节标 ❌，建议下次重跑。
- 抓取到 HTML 但无符合时间窗的条目 → `status="empty"`，标 ⚠️（可能是上游结构调整或确实缺内容）。
- git.postgresql.org 可能被 anti-bot 拦截 → `status="human_required"`，调用 `references/human-verification.md` 中的兜底：先 `mcp__MiniMax__web_search` 搜近 7 天 `postgresql.git commit Michael Paquier` / `Heikki Linnakangas` 等核心 committer 名，从搜索摘要凑出关键 commit 列表。
- aibase.com / ai-bot.cn 内容可能包含微信公众号跳转链接，优先保留公众号原文链接而非落地页。

### Step 4. 分类汇总

按以下 5 章输出：

1. **🐘 PostgreSQL 生态** —— #1–#5 源，按子类聚合：内核提交（含 commit hash + 作者 + 一句话）、社区博客、PostGIS、官方公告。
2. **🦆 其他数据库（DuckDB 等）** —— #6 源。
3. **🤖 AI 新闻** —— #7、#8 源，国内为主，去重合并同主题条目（如"Seedance 2.0 mini"在 aibase 和 ai-bot 都有时合并为一条，标注双源）。
4. **⭐ GitHub 趋势项目（weekly）** —— #9 源，含仓库名、描述、star 增量、语言。
5. **📄 AI 论文（HuggingFace Trending）** —— #10 源，含论文标题、机构、摘要、链接、热度指标。

每章首段放一个 mermaid 图（见 Step 5）。

### Step 5. Mermaid 图表

按 `references/output-template.md` 中的模板，固定生成以下图（即使某些源失败，对应图表也保留框架并标注缺失）：

- **开篇 pie 图**：本周条目分类占比（5 大类 + 失败/空响应）。
- **timeline 图**：近 7 天每日发布密度，重要事件挂时间线上。
- **PG 内核 mindmap**：本周 PG 内核变更主题（逻辑复制 / pg_restore / RI 快路径 / XML / 类型 / 其他）。
- **AI 主题 mindmap**：开源模型 / Coding Agent / 视频生成 / 行业整合 / 智能体工具链。
- 视数据情况可加 **GitHub trending 分类饼图**、**论文主题旭日图**（mermaid 不支持时用 markdown 列表替代）。

### Step 6. 数据源覆盖表

固定章节（七、数据源覆盖），表格列：`# | 类别 | 源 | 状态 | 抓到条目数 | 备注`。

状态枚举：

- ✅ `ok`：≥1 条命中时间窗。
- ⚠️ `empty`：HTTP 200 但无近 7 天条目。
- ❌ `error`：HTTP 非 2xx / 网络异常。
- 🙋 `human_required`：anti-bot 或需浏览器验证，按 `references/human-verification.md` 兜底。

### Step 7. 写入 markdown

- 路径：`<cwd>/markdown/db-ai-weekly-YYYY-MM-DD.md`（若 `markdown/` 不存在则创建）。
- 命名：当天日期。如果当天文件已存在，文件名追加 `-HHMM` 后缀避免覆盖。
- 文件末尾追加一行：`*本周报由 db-ai-github-paper-weekly-news skill 于 YYYY-MM-DD HH:MM 自动生成。条目均附原始来源链接，请以原文为准。*`

## 关键规则

1. **不编造条目** —— 抓不到就标 ⚠️，绝不凭训练记忆补内容（参考用户 `feedback_verify_before_writing`）。
2. **跨源同主题合并** —— AI 新闻常有多源覆盖，合并时优先保留最早发布时间，标题取最完整版本。
3. **保留原链接** —— 每条条目附原始 URL；公众号文章保留 mp.weixin.qq.com 链接。
4. **中文为主** —— aibase / ai-bot 已是中文，保留原标题；英文源（postgresweekly / duckdb / github / huggingface）翻译或保留英文均可，但标签用中文（如"内核""逻辑复制""视频生成"）。
5. **遵循 `~/.claude/CLAUDE.md` 的 WebSearch 规则** —— 用 `mcp__MiniMax__web_search` 而非内置 `web_search`。
6. **章节顺序固定** —— 七章结构按模板，便于跨周对比。

## 资源

- `scripts/crawl.py` — 10 源抓取编排（动态 URL 解析 + 并行抓取 + 错误归类）。
- `scripts/parse_postgresweekly.py` — postgresweekly.com 专用，解析最新 issue 编号。
- `scripts/parse_postgres_git.py` — git.postgresql.org shortlog 解析（含 human_required 兜底）。
- `scripts/render_report.py` — 把抓取结果渲染为最终 markdown。
- `references/output-template.md` — markdown 模板（章节结构 + mermaid 片段）。
- `references/human-verification.md` — anti-bot 源兜底方案。

## 触发词

- "生成 db-ai-weekly 周报"
- "跑一次本周数据库+AI+GitHub+论文汇总"
- "weekly news 抓一下"
- "本周 pg + ai 速览"