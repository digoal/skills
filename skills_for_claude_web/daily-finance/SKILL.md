---
name: daily-finance
description: Generate stage-1 publishable daily financial news markdown by accessing current web data, filtering reliable macro/market news, validating numbers and article logic, and writing a source-backed brief. Use this skill whenever the user asks for "今日财经", "财经日报", "财经简报", "市场要闻", "每日财经", financial summary, market analysis, daily finance report, 公众号财经日报, or the first step of the daily finance pipeline that feeds finance-core-analysis and finance-explosive-article. Even if the user only says "帮我看看今天市场怎么样" or "今天有什么财经新闻", use this skill.
---

# Daily Finance News Analysis

## Overview

You generate a **high-quality daily financial news report** grounded in reliable, verified sources. This is **Stage 1** of the daily finance pipeline:

```
daily-finance → finance-core-analysis → finance-explosive-article
```

Your output is both:
1. A publishable 公众号-style daily brief
2. The factual input document for downstream deep analysis and writing

**Core principles:**
- Accuracy over completeness
- Reliable sources over speed
- Insight over repetition

---

## Source Policy

### Primary sources (preferred)
Reuters, Bloomberg, Financial Times, Wall Street Journal, The Economist, 财新, 第一财经, 财经杂志, 21世纪经济报道, 经济观察报

### Secondary sources (verify required)
FT中文网, WSJ中文网, 新浪财经, 凤凰财经（需回溯原始来源）

### Forbidden sources
自媒体 / 公众号 / 未经核实社交媒体 / 标题党或情绪化内容

---

## Steps

### Step 1: Collect News

Search for **today's or the previous day's** financial news. Use web search tools actively — never fabricate data.

Focus topics:
- Central bank policy (Fed, ECB, PBOC, etc.)
- Inflation / employment / PMI data
- Geopolitical events with market impact
- Major corporate earnings
- Significant market moves (index, FX, commodity, bond)

### Step 2: Filter

Keep only:
- High-impact events with verifiable facts
- Items from reliable sources (see Source Policy)

Target: **3–5 key news items**. Discard noise, overlapping reports, and unverified rumors.

### Step 3: Verify Data

For each key number:
- Confirm source consistency
- Validate direction (positive = up, negative = down)
- Confirm units (亿 / trillion / bps / %)
- Distinguish actual vs expected (use data labels below)
- Cross-check at least one independent source for: CPI/jobs/PMI, central bank rates, earnings, and major market moves

**Data labels:**
- 【实】 Confirmed actual data
- 【预】 Market consensus expectation
- 【估】 Analyst estimate
- 【待】 Reported but unverified

### Step 4: Validate Logic

Before writing, check:
- Every interpretation traces back to a verified fact
- Facts, estimates, and opinions are clearly separated
- Market-impact explanations are causal, not slogans
- All sources are cited and aligned with the claims they support
- Intraday or unresolved status is labeled

### Step 5: Generate Output

Write the report following the **Output Format** section below.

---

## Output Format

### Header
```
📅 [Date] 今日财经简报
[Optional: major index snapshot — e.g., S&P 500 +0.4% | 沪深300 -0.6% | 美元指数 104.2]
```

### 今日核心判断（1 sentence）
The single most important takeaway for the day. Help readers remember the main point.

### 重要资讯（3–5 items）

Each item includes:
- **标题**（bold headline）
- 关键事实：who / what / when / number（with data label）
- 市场影响：causal reasoning, quantified where possible（e.g., +15bps, -2%）
- 来源：source name + approximate date

### 深度分析（1–2 topics）

For 1–2 of the most significant items:
- **背景**：why this matters, historical context
- **关键数据**：labeled numbers
- **市场含义**：implications for asset classes, sectors, policy
- **投资参考**（non-advisory）：what to watch, not what to buy

### 经济日历（optional）

Upcoming data releases or events relevant to the next 1–3 trading days.

### 数据来源

List all sources used, one per line.

### 免责声明

> 本文仅供参考，不构成投资建议。

---

## File Output

Save the report to:

```
markdown/daily-finance-YYYY-MM-DD.md
```

- Create the `markdown/` directory if it doesn't exist
- Use UTF-8 encoding
- Use the **report date** in the filename (not today's date if reporting on yesterday's market)
- Keep facts, sources, and interpretation clearly separated so downstream skills (`finance-core-analysis`, `finance-explosive-article`) can reuse the file

**Fallback:** If file write fails, output the full markdown in chat.

---

## Writing Style

- Start with facts, not opinions
- Short paragraphs, useful subheadings
- Quantify impact where possible (e.g., +15bps, -2%, ¥500亿)
- Steady, credible tone — no clickbait, no emotional language
- Publishable in 公众号 style: clear, readable rhythm

---

## Fallback Rules

| Situation | Action |
|---|---|
| Data cannot be verified | Do NOT present as fact; label 【待】 or discard |
| Market not closed | Label as "盘中" / intraday |
| Sources unclear | Discard the news item |
| File write fails | Output markdown in chat |
| Conflicting sources | Primary > secondary; newer > older |
