---
name: finance-core-analysis
description: Generate stage-2 deep financial mechanism analysis markdown from a daily-finance brief plus current web verification. Use this skill whenever the user wants deeper macro/market analysis beyond daily news, asks for "核心分析"、"深度分析"、"机制分析"、"为什么市场这样走"、"帮我分析一下背后逻辑", or when the user references a daily-finance output and wants the second step of the pipeline before writing a 公众号爆款文章. Even if the user only says "深挖一下今天的市场" or "帮我分析这份财经简报", use this skill. This skill feeds finance-explosive-article as stage 2 of: daily-finance → finance-core-analysis → finance-explosive-article.
---

# Core Financial Analysis

## Overview

Generate a **deep mechanism analysis** grounded in stage-1 daily finance facts plus live-verified data.

Pipeline position:
```
daily-finance → finance-core-analysis → finance-explosive-article
```

Your output is a standalone, publishable 公众号 deep-analysis article — rigorous enough to stand alone, structured enough to feed the final explosive article downstream.

---

## Input

**Preferred:** Read `markdown/daily-finance-YYYY-MM-DD.md`

**Fallback order:**
1. Ask for the report date or file path if ambiguous
2. If user pastes raw daily-finance content in chat, use that
3. Never invent missing facts

---

## Step 1: Verify & Update Data

Always access current external data before writing.

Use web search / browser / MCP tools to:
- Re-check major market prices, yields, FX rates, commodities, volatility indices
- Verify policy statements, macro releases (CPI/PMI/jobs), earnings, geopolitical facts
- Update stale numbers from the stage-1 brief when newer reliable data is available

**Source hierarchy:**
- **Primary:** Official releases, central banks, exchanges, regulators, company filings; Reuters, Bloomberg, FT, WSJ
- **Chinese primary:** 财新, 第一财经, 财经杂志, 21世纪经济报道, 经济观察报
- **Secondary (require source backtracking):** FT中文网, WSJ中文网, 新浪财经

Only add data that is source-verifiable. Never fabricate.

---

## Step 2: Apply the Core Model

Explain market behavior through these variables:

| Variable | What to examine |
|---|---|
| **流动性** Liquidity | Money supply, repo rates, bank reserves, credit conditions |
| **利率** Interest rates | Real vs nominal; short vs long end; central bank signals |
| **风险偏好** Risk appetite | VIX, credit spreads, EM flows, positioning |
| **资本流动** Capital flows | Cross-border flows, DXY, CNY pressure, EM vs DM |
| **政策方向** Policy | Fiscal, monetary, regulatory — direction and credibility |
| **资产负债表压力** Balance sheets | Corporate leverage, bank stress, sovereign debt |
| **激励约束** Incentive constraints | What is forcing or preventing capital allocation |

**Causal chain template:**
```
事件 → 约束变化 → 资金行为 → 定价结果 → 风险信号
```

Use this chain to anchor every mechanism explanation.

---

## Step 3: Validate Before Writing

Check every item:

- **Data:** Dates correct? Units right? Directions accurate? Actual vs expected labeled? Intraday vs close distinguished?
- **Sources:** Important claims have reliable sources?
- **Logic:** Every conclusion follows from a mechanism, not mood words?
- **Causal chain:** Event → constraint → capital behavior → pricing result → risk signal present?
- **Counter-case:** Does the analysis include what would prove it wrong?
- **Publishability:** Title, subheadings, short paragraphs, clear conclusion?

---

## Output Format

### 1. Title
公众号-style: tension + mechanism. Prefer substance over clickbait.

### 2. 核心判断（Executive Judgment）
One paragraph: the single most important market judgment today, and what specifically changed.

### 3. 事实基础（Fact Base）
- Inherit 3–5 key facts from daily-finance with source labels 【实】【预】【估】【待】
- Add newly verified data where necessary, clearly marked
- No invented facts

### 4. 机制分析（Mechanism Analysis）
Analyze through **3–5 relevant lenses** from the core model. For each lens:
- What changed
- Why it matters
- How it transmits into asset prices

Use "不是A，而是B" contrast structure where helpful to clarify mechanism.

### 5. 核心矛盾（Core Contradiction）
Name the central tension driving the current market, e.g.:
- 增长 vs 通胀
- 政策宽松 vs 汇率压力
- 风险偏好修复 vs 盈利压力
- 流动性改善 vs 资产负债表收缩

### 6. 情景推演（Scenario Deduction）

| 情景 | 触发条件 | 资产含义 |
|---|---|---|
| 基准情景 | ... | ... |
| 备选情景 | ... | ... |
| 证伪信号 | ... | ... |

### 7. 关键跟踪变量（Variables to Watch）
3–6 observable indicators for the next update cycle.

### 8. 方向性参考（Non-Advisory Implication）
Explain directional exposure and risk. No ticker calls, no buy/sell recommendations.

### 9. 数据来源
Inherited sources from daily-finance + any new verified sources, one per line.

### 10. 免责声明
> 本文仅供参考，不构成投资建议。

---

## File Output

Save to:
```
markdown/finance-core-analysis-YYYY-MM-DD.md
```

- Use the **same report date** as the input daily-finance file
- Create `markdown/` directory if missing
- UTF-8 encoding
- Output a complete publishable article, not notes
- **Fallback:** If write fails, output full markdown in chat

---

## Writing Style

- Strong title, short paragraphs, numbered sections
- Sharp but rational tone — serious analysis, not hype
- Mechanisms explained in plain Chinese
- Use contrast: "不是A，而是B"
- No empty emotional phrases, no unexplained jargon
- Publishable as-is on 公众号

---

## Goal

Answer four questions every reader should leave with:

1. **What changed** — the key fact
2. **Why it changed** — the mechanism
3. **How facts connect to asset pricing** — the transmission
4. **What would prove this wrong** — the falsification signal
