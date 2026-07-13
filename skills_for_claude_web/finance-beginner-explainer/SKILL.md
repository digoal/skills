---
name: finance-beginner-explainer
description: Explain a finance-explosive-article markdown file for readers with weak financial knowledge by unpacking concepts, causal chains, examples, analogies, and transferable analysis methods. Use this skill whenever the user asks to "帮小白看懂"、"用简单语言解释"、"写一篇入门版"、"解读一下这篇文章"、"财经扫盲"、"怎么看懂这个市场"、turn a 德哥爆款文章 into a beginner guide, or produce stage-4 output of the daily finance pipeline. Even if the user only says "帮我把这篇文章讲得更通俗一点" or "普通人怎么理解这个", use this skill. This is stage 4 of: daily-finance → finance-core-analysis → finance-explosive-article → finance-beginner-explainer.
---

# Finance Beginner Explainer

## Overview

Transform `finance-explosive-article-YYYY-MM-DD.md` into a **beginner-friendly companion article** that teaches readers not only what the original says, but **how to reason through similar financial events independently**.

Pipeline position:
```
daily-finance → finance-core-analysis → finance-explosive-article → finance-beginner-explainer
```

The goal is not to simplify or water down — it is to **unpack every causal link** so a reader with no finance background walks away with a reusable mental model.

---

## Step 1: Read Inputs

**Preferred:** Read all available upstream files:
- `markdown/finance-explosive-article-YYYY-MM-DD.md` ← primary source
- `markdown/finance-core-analysis-YYYY-MM-DD.md` ← mechanism and scenarios
- `markdown/daily-finance-YYYY-MM-DD.md` ← verified facts and sources

**Fallback order:**

| Situation | Action |
|---|---|
| Multiple dates exist, no date given | Use the newest file by date; state that assumption at top of output |
| No upstream file exists | Ask for the article file or pasted content |
| Claim in source is unclear | Mark it as interpretation with uncertainty note |

Never invent facts. If a number or claim cannot be traced to upstream files, do not include it.

---

## Step 2: Extract the Original Argument

Before writing, identify and note internally:

- **Core judgment**: the article's single most important conclusion
- **The reversal**: the "不是A，而是B" insight
- **Causal chain**: usually `触发事件 → 传导机制 → 资金行为 → 资产定价 → 风险约束 → 后续观察点`
- **Key numbers**: source-backed data with labels 【实】【预】【估】【待】
- **Falsification signals**: what would prove the article wrong

---

## Step 3: Translate Concepts for Beginners

For every important financial term, **explain it in plain Chinese before using it heavily**.

Priority terms to unpack:

| Term | Unpack before use |
|---|---|
| 风险偏好 Risk appetite | ✅ |
| 流动性 Liquidity | ✅ |
| 通胀预期 Inflation expectation | ✅ |
| 利率传导 Interest-rate transmission | ✅ |
| 贴现率与估值 Discount rate / valuation | ✅ |
| 资本流动 Capital flows | ✅ |
| 资产负债表压力 Balance-sheet pressure | ✅ |
| 风险溢价 Risk premium | ✅ |
| 长久期资产 Long-duration assets | ✅ |
| 汇率约束 Currency constraint | ✅ |

> Use simple analogies to introduce, but **do not let analogies replace the actual mechanism**. Always return to the real economic logic after the analogy.

---

## Step 4: Expand the Logic Chain

For each arrow in the causal chain, explain using this four-part pattern:

1. **是什么** — What does this step mean?
2. **为什么** — Why does this happen? (incentive / economic logic)
3. **怎么传导** — How does it affect the next link?
4. **怎么验证** — What observable data confirms or falsifies it?

**Example expansion:**
```
油价上涨 → 通胀预期上升 → 降息预期下降 → 利率维持高位 → 成长股估值承压
```
Each `→` gets its own four-part explanation — not just a label.

---

## Step 5: Add Examples and Transfer

Include all four of the following:

1. **生活类比** — One everyday analogy that makes the mechanism intuitive
2. **市场例子** — One concrete market example from the article (with numbers)
3. **举一反三** — One example showing how the **same model** applies to a *different* scenario; must teach a reusable method, not just repeat the original case
4. **常见误区** — One common beginner mistake and how to avoid it

---

## Output Format（MANDATORY STRUCTURE）

### 1. 标题
Beginner-friendly title that signals "this is your guide to understanding X."

### 2. 这篇文章到底在讲什么
2–3 sentences: the core judgment and reversal in plain Chinese. No jargon yet.

### 3. 小白先懂这几个概念
Define 3–5 key terms used in the article. Short, plain, one analogy each.

### 4. 原文逻辑链条逐层拆解
Walk through each link of the causal chain using the four-part pattern (是什么 / 为什么 / 怎么传导 / 怎么验证).

### 5. 用一个生活例子重新讲一遍
Retell the entire mechanism using an everyday scenario. End by mapping it back to the financial case.

### 6. 用一个市场例子验证这条链
Use a concrete market data point or event from the article to show the chain working in real life.

### 7. 举一反三：下次遇到类似新闻怎么分析
Show how the same model applies to a different but structurally similar situation. Give the reader a step-by-step method.

### 8. 最容易误解的地方
Name 1–2 common beginner mistakes. Explain why people make them and what the correct reasoning is.

### 9. 小白分析清单
A short checklist (5–8 items) readers can use when they encounter similar news next time.

### 10. 总结
2–3 sentences: the one model to remember, and one question the reader should now be able to answer.

### 11. 来源与风险提示
- Inherited sources from upstream files
- `本文仅供学习交流，不构成投资建议。`

---

## File Output

Save to:
```
markdown/finance-beginner-explainer-YYYY-MM-DD.md
```

- Use the **same report date** as the source `finance-explosive-article` file
- Create `markdown/` directory if missing
- UTF-8 encoding
- **Fallback:** If write fails, output full markdown in chat

---

## Quality Rules

- Preserve source-backed facts from upstream articles; do not alter numbers
- Clearly separate **fact**, **interpretation**, and **teaching analogy**
- Explain causal mechanisms; never use "情绪推动" without unpacking the underlying incentive
- No explicit buy/sell recommendations
- Do not add dramatic claims for readability
- Do not talk down to readers — treat them as intelligent adults learning something new

---

## Quick Validation Checklist

Before finalizing, verify:

- [ ] Output explains the original core judgment
- [ ] Every major causal arrow is unpacked in beginner language (4-part pattern)
- [ ] Includes: everyday analogy, market example, 举一反三, common mistake
- [ ] 小白分析清单 is present and actionable
- [ ] Output filename date matches upstream article date
- [ ] Final disclaimer is present: `本文仅供学习交流，不构成投资建议。`
