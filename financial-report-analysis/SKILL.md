---
name: financial-report-analysis
description: Analyze company annual reports, quarterly reports, 10-K/10-Q filings, earnings releases, shareholder letters, or financial-report PDFs/URLs/files and produce a professional Chinese Markdown report for ordinary investors. Use when the user provides a company financial report address or local file and asks for 财报分析, 年报解读, 季报解读, 10-K/10-Q analysis, earnings analysis, investment reference, accounting red-flag detection, valuation discussion, or beginner-friendly explanation saved to the current project's markdown directory.
---

# Financial Report Analysis

## Goal

Generate a Chinese Markdown financial-report analysis for ordinary investors, written from the perspective of a senior financial analyst, fund manager, and investment-bank analyst. Save the final `.md` file under the current project's `markdown/` directory.

## Workflow

1. Ingest the report.
   - Accept a URL, PDF, HTML filing, text file, spreadsheet, or local document.
   - Prefer official sources: SEC/EDGAR, exchange filings, company investor-relations pages, audited annual reports, and earnings releases.
   - For recent market prices, current valuation multiples, analyst estimates, regulation, or news-sensitive facts, verify with current web sources and cite them.
   - If the report is long, extract the table of contents, MD&A, financial statements, notes, risk factors, segment data, cash-flow statement, and accounting-policy notes first.

2. Build the data spine before writing opinions.
   - Identify reporting period, currency, accounting standard, consolidation scope, restatements, and comparability issues.
   - Extract revenue, gross profit, operating profit, net income, EPS, operating cash flow, free cash flow, capex, cash, debt, equity, AR, inventory, goodwill, R&D, share count, segment/geographic revenue, and management guidance.
   - Compare year over year and, when available, sequentially. State whether each conclusion comes from reported data, calculation, management commentary, or external verification.

3. Read `references/analysis-framework.md` when preparing the analysis.
   - Use it as the checklist for core questions, accounting traps, hidden risks, business-model transitions, valuation scenarios, and Tesla-style deep-dive questions.
   - Do not paste the checklist mechanically; select what matters for the company and explain why.

4. Write for two audiences at once.
   - Give institutional-quality judgment, but explain specialist terms in plain language at first use.
   - For every important ratio or accounting term, add the business logic: "why this number matters", "what can go wrong", and "what a normal investor should check next".
   - Use examples and counterexamples when they clarify a causal chain.

5. Produce an investment-reference view, not personalized financial advice.
   - Provide a clear stance such as `积极关注`, `中性观望`, `谨慎`, or `回避`, with explicit assumptions.
   - Separate base, bull, and bear cases. Explain what evidence would make the view change.
   - If valuation depends on speculative businesses, value the mature business and option-like business separately.

6. Save the output.
   - Create `markdown/` in the current project if needed.
   - Use a deterministic filename such as `markdown/<company>-<period>-financial-report-analysis.md`.
   - Include source links or local file names, extraction date, and a short limitation note for missing or unaudited data.

## Required Markdown Structure

Use this structure unless the user asks for a different format:

```markdown
# <公司> <期间>财报深度解读

## 0. 结论先行
## 1. 这家公司到底靠什么赚钱
## 2. 收入结构与增长质量
## 3. 毛利率、费用率与盈利能力
## 4. 现金流与利润质量
## 5. 资产负债表健康度
## 6. 财报里的坑与反常信号
## 7. 业务前景与关键变量
## 8. 估值与投资参考
## 9. 小白投资者应该学会的分析方法
## 10. 关键风险、反证条件与后续跟踪清单
## 数据来源与局限
```

## Quality Bar

- Be sharp, but do not overclaim. Tie every strong opinion to report data, historical comparison, peer comparison, management disclosure, or authoritative external evidence.
- Do not generalize from one isolated example. If using cases such as 康美药业, Enron, WorldCom, WeWork, GE, Amazon AWS, Apple services, Adobe subscription transition, or Netflix content-capex debates, state what the case proves and what it does not prove.
- Surface assumptions. If an assumption breaks, provide the alternative interpretation instead of forcing the original thesis.
- Distinguish accounting profit from cash profit, growth from growth quality, and valuation from business quality.
- For Chinese output, keep professional terms in Chinese with English abbreviations where useful, for example `经营活动现金流 OCF` and `自由现金流 FCF`.
