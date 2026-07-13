---
name: finance-explosive-article
description: Generate stage-3 high-impact 德哥风格 公众号 financial articles from daily-finance and finance-core-analysis outputs plus current web verification. Use this skill whenever the user wants a 公众号爆款文章, final financial commentary, "帮我写成文章"、"整理成爆款"、"德哥风格"、"公众号推文"、"写一篇深度文章"、"把分析写成文章发布", or the third and final step of the pipeline. Even if the user only says "帮我把今天的分析整理一下发出去", use this skill. This is stage 3 of: daily-finance → finance-core-analysis → finance-explosive-article.
---

# 德哥风格金融爆款文章

## Overview

Generate a **high-impact, publishable financial article** in 德哥风格 for 公众号.

Pipeline position:
```
daily-finance → finance-core-analysis → finance-explosive-article
```

- **Stage 1** supplies facts and verified sources
- **Stage 2** supplies mechanisms, scenarios, and key variables
- **Stage 3 (this skill)** transforms them into a sharp, viral-ready article

The goal is NOT to summarize news. The goal is to:
- Explain what is **really** happening beneath the surface
- Identify the underlying drivers
- Deliver sharp, data-backed insight
- Make readers say: **"原来是这样"**

---

## Step 1: Read Inputs

**Preferred:** Read both upstream files:
- `markdown/daily-finance-YYYY-MM-DD.md`
- `markdown/finance-core-analysis-YYYY-MM-DD.md`

**Fallback order:**
| Situation | Action |
|---|---|
| Only `daily-finance` exists | Build mechanism yourself; mark uncertainty explicitly |
| Only `finance-core-analysis` exists | Use its facts/sources; avoid unsupported news details |
| Date ambiguous | Ask the user which date to use |
| User pasted content in chat | Use that content directly |

---

## Step 2: Verify Key Data

Always access current external data before writing.

Use web search / browser / MCP tools to:
- Confirm upstream facts are still accurate
- Re-check any number used in the **title, opening, or core judgment**
- Update stale data when a reliable newer source exists

**Do not** add fresh claims only for dramatic effect. Every number must be source-traceable.

**Source hierarchy:**
- Primary: Reuters, Bloomberg, FT, WSJ; 财新, 第一财经
- Secondary (require backtracking): FT中文, WSJ中文, 新浪财经
- Forbidden: 自媒体, 公众号, 未经核实社交媒体

---

## Step 3: Apply 德哥风格

Three mandatory elements:

### 3a. First-Principles Mechanism

Never explain surface events. Explain the bottom-layer driver.

Every conclusion must trace to at least one:
- 流动性 Liquidity
- 利率 Interest rates
- 风险偏好 Risk appetite
- 资本流动 Capital flows
- 政策方向 Policy direction
- 资产负债表压力 Balance-sheet pressure
- 激励约束 Incentive constraints

### 3b. Counterintuitive Reversal（必须有）

The article **must** contain a clear "不是A，是B" cognitive reversal that exposes a real mechanism mismatch — not wordplay.

**Strong examples:**
- "这不是牛市回来了，而是流动性重新定价风险资产。"
- "市场不是在买增长，而是在买利率下行的想象空间。"
- "政策不是直接托底价格，而是在修复资产负债表预期。"

**Banned phrases (replace with mechanisms):**
- ❌ "因为利好所以涨"
- ❌ "市场情绪推动"
- ❌ "资金炒作"
- ❌ "政策刺激"

### 3c. Reusable Systemic Model（必须有）

Every article must leave the reader with one model they can reuse.

**Standard causal chain:**
```
触发事件 → 传导机制 → 资金行为 → 资产定价 → 风险约束 → 后续观察点
```

Name the model in plain Chinese when useful:
- "流动性-风险偏好模型"
- "美元利率-全球资金流模型"
- "政策预期-资产负债表模型"

---

## Step 4: Validate Before Writing

| Check | Requirement |
|---|---|
| **Data** | Dates, units, directions correct? Actual vs expected labeled? Intraday vs close distinguished? |
| **Sources** | Every key number traceable to upstream files or reliable external source? |
| **Reversal logic** | "不是A，是B" supported by mechanism, not rhetoric? |
| **Causal chain** | Trigger → mechanism → capital behavior → asset pricing → risk constraint → next signal? |
| **Publication** | Title, opening, section rhythm, conclusion, sources, disclaimer all present? |
| **Risk boundary** | No explicit buy/sell recommendation? |

> If a powerful sentence overstates the evidence, weaken the sentence — never weaken the facts.

---

## Output Format（MANDATORY STRUCTURE）

### 1. 爆点标题
- Must create tension or contradiction
- Must trigger curiosity
- Prefer "不是A，是B" or "真正的X，不是Y"
- ✅ "市场根本不是在涨，而是在赌一件事"
- ✅ "所有人都在看政策，真正的变量却在资金价格"
- ❌ Generic headlines without tension

### 2. 破题（Opening）
- Start with a **fact or anomaly**
- Immediately raise the core question
- State the mistaken mainstream interpretation
- Foreshadow the counterintuitive answer

### 3. 一句话反转（Core Judgment）
One direct sentence defining the article's central reversal:
> `这件事表面上是A，本质上是B。`

Then explain why A is incomplete and B is the real pricing variable.

### 4. 核心逻辑（Core Analysis）
2–4 sections, each containing:
- Mechanism explanation
- Data or observable signals
- Causal reasoning
- Link back to the systemic model

Typical angles: Liquidity / Policy / Global capital flows / Sector rotation

### 5. 可复用模型（System Model）
Summarize the reusable model explicitly:
```
第一层：触发变量 — ...
第二层：传导机制 — ...
第三层：资产定价 — ...
第四层：验证信号 — ...
```

### 6. 关键判断（Key Insight）
Clearly state:
- What the market is actually pricing
- What most people misunderstand
- Which variable matters most next

### 7. 推演（Scenario Analysis）
| 情景 | 触发条件 | 资产含义 |
|---|---|---|
| 基准情景 | ... | ... |
| 备选情景 | ... | ... |
| 证伪信号 | ... | ... |

### 8. 方向性参考（Non-Advisory Implication）
Directional thinking only. No ticker calls, no buy/sell.

### 9. 收束（Closing）
- Strong summary sentence
- End with mechanism, not slogan

### 10. 数据来源
Short source list, one per line.

### 11. 免责声明
> 本文仅供参考，不构成投资建议。

---

## File Output

Save to:
```
markdown/finance-explosive-article-YYYY-MM-DD.md
```

- Use the **same report date** as upstream files
- Create `markdown/` directory if missing
- UTF-8 encoding
- Final article only — no process notes
- **Fallback:** If write fails, output full markdown in chat

---

## Writing Style

- Short paragraphs, clear rhythm
- Sharp and direct — no fluff, no academic tone
- Use contrast: "不是A，而是B"
- Declarative sentences preferred
- Use "说白了", "真正的问题是", "底层逻辑是" sparingly but decisively
- Do not stack metaphors
- Start with tension → land on mechanism → close with model

---

## Goal

Produce an article that:
1. Makes the reader say **"原来是这样"**
2. Leaves behind **one reusable model**
3. Can spread on social platforms
4. Builds authority and trust through factual precision
