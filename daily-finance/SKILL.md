---
name: daily-finance
description: Generate stage-1 publishable daily financial news markdown by accessing current web data, filtering reliable macro/market news, validating numbers and article logic, and writing a source-backed brief. Use when user asks for "今日财经", financial summary, market analysis, daily finance report, 公众号财经日报, or the first step of the daily finance pipeline that feeds finance-core-analysis and finance-explosive-article.
---

# Daily Finance News Analysis

## Overview
You generate a **high-quality daily financial news report** based on reliable sources, including macro trends, market movements, and key events.

This is stage 1 of the daily finance pipeline:

`daily-finance → finance-core-analysis → finance-explosive-article`

Your output is both a publishable 公众号-style daily brief and the factual input document for downstream deep analysis and 德哥风格公众号 writing.

Focus on:
- Accuracy over completeness
- Reliable sources over speed
- Insight over repetition

---

## When to use

Use this skill when the user asks for:

- 今日财经 / 财经日报 / 市场要闻
- Daily financial news summary
- Market analysis or macro overview
- Financial briefing for today

---

## Date and scope resolution

Before collecting news, determine the report date and market scope:

- If the user says "today", use the user's current local date; if major target markets are still trading, label market data as intraday.
- If the user gives a date, use that date and prefer sources published on that date or the following morning when they report closing data.
- If no region is specified, cover global macro plus the most relevant US, China, Hong Kong, currency, rates, and commodity signals.
- If the news day is thin, produce fewer high-quality items instead of padding weak stories.

Record these assumptions in the header so downstream skills can reuse the report without guessing.

---

## Source policy

### Primary sources (preferred)
- Reuters
- Bloomberg
- Financial Times
- Wall Street Journal
- The Economist
- 财新 / 第一财经 / 财经杂志 / 21世纪经济报道 / 经济观察报

### Secondary sources (verify required)
- FT中文网 / WSJ中文网
- 新浪财经 / 凤凰财经（需回溯来源）

### Forbidden sources
- 自媒体 / 公众号
- 未经核实社交媒体
- 标题党或情绪化内容

---

## Tool policy

Use available tools to search for current financial news:

- Prefer web search / browser / MCP tools
- Always access current external data when generating a current-day report
- If multiple sources conflict:
  - Primary source > secondary source
  - Newer report > older report

Never fabricate data.

---

## Steps

### 1. Collect news
- Focus on **today or previous day**
- Topics:
  - Central banks
  - Inflation / employment
  - Geopolitics
  - Earnings
  - Major market moves

For each candidate item, capture:

| Field | Requirement |
|---|---|
| Event | Who did what, and when |
| Number | Actual value, expectation/previous value if available |
| Market reaction | Asset, direction, magnitude, timestamp/close status |
| Source | URL/title/publication time or clearly named source |
| Why it matters | One causal sentence, not a slogan |

---

### 2. Filter
Keep only:
- High-impact events
- Verifiable facts
- Reliable sources

Target: **3–5 key news items**

Discard items that are merely commentary, low-liquidity price moves, single-stock anecdotes with no broader implication, or duplicated versions of the same story.

---

### 3. Verify data
For each key number:

- Check source consistency
- Validate:
  - % direction (positive = up, negative = down)
  - Units (亿 / trillion / %)
  - Time context (actual vs expected)
- Cross-check at least one independent source for important market moves, rates, CPI/jobs/PMI data, policy statements, and earnings numbers when available

Use this evidence rule:

- Core judgment: at least two reliable sources or one official/primary source.
- Routine market snapshot: one authoritative market-data source is acceptable.
- Reported but not confirmed detail: label `【待】` and do not use it as the article's main conclusion.

---

### 4. Validate article logic

Before final output, check:

- Does every interpretation trace back to a verified fact?
- Are facts, estimates, and opinions clearly separated?
- Is the market-impact explanation causal rather than slogan-like?
- Are all sources listed and aligned with the claims they support?
- Are uncertainty and intraday status labeled?

---

### 5. Generate output

## Required sections

### Header
- Date
- Report scope and market status
- Data freshness note, e.g. close / intraday / previous session
- Optional: major index snapshot

### 今日核心判断
- One sentence stating the main verified market signal.
- One sentence explaining the mechanism behind it.

### Key News (3–5 items)
Each must include:
- Title
- Key facts (who / what / when)
- Market impact
- Source

### Deep Analysis (1–2 topics)
- Background
- Key data
- Market implications
- Investment insight (non-advisory)

### Sources
- List all sources used

### Disclaimer
本文仅供参考，不构成投资建议。

---

## Optional sections (if data available)

- Macro overview
- Sector trends
- Economic calendar

---

## Data labels

Use clear tags:

- 【实】 actual confirmed data
- 【预】 market expectation
- 【估】 estimation
- 【待】 unverified / reported

---

## Fallback rules

- If data cannot be verified → do NOT present as fact
- If market not closed → label as intraday / pending
- If sources unclear → discard the news
- If external data access fails → use only user-provided or already available source-backed facts and state the limitation in the header
- If fewer than 3 reliable items exist → publish 1–2 items plus an explicit "今日可验证信息有限" note
- If unable to save file → output markdown in chat

---

## File output

If environment allows:

Save to:

`markdown/daily-finance-YYYY-MM-DD.md`


Rules:
- Create directory if missing
- Use UTF-8 encoding
- Use the report date in the filename
- Keep facts, sources, and interpretation clearly separated so downstream skills can reuse the file
- If write fails → fallback to chat output

---

## Writing style

- Start with facts, not opinions
- Separate facts from interpretation
- Avoid exaggeration
- Use quantified impact (e.g., +15bps, -2%)
- Write in publishable 公众号 style: clear title, short paragraphs, useful subheadings, readable rhythm
- Keep the tone steady and credible; do not use clickbait or emotional language
- Include one "今日核心判断" so readers remember the main point

---

## Goal

Produce a report that is:

- Reliable (source-backed)
- Structured (easy to read)
- Insightful (not just aggregation)
