---
name: paper-interpretation
description: 从论文 PDF 文件或论文 PDF URL 生成通俗易懂、图文并茂、带批判性评估的中文 Markdown 解读，并保存到当前项目的 markdown 目录。Use when the user asks to interpret,精读,解读,summarize,explain,analyze, or write an article from an academic paper PDF, arXiv PDF, conference paper PDF, journal paper PDF, or local/remote PDF URL.
---

# Paper Interpretation

## Goal

Read the whole paper, including text, tables, figures, captions, appendices, and experiment details, then write a Chinese Markdown article that helps non-specialists understand the paper while preserving its academic and industrial value.

Always save the final Markdown under the current project's `markdown/` directory. Create the directory if missing. Use a descriptive filename derived from the paper title, for example `markdown/论文标题-通俗解读.md`.

## Intake

Accept either:

- A local PDF path.
- A PDF URL.

If the user gives a URL, download the PDF or use `scripts/extract_paper_assets.py` to download and extract it. If the PDF is scanned or extraction is incomplete, use OCR or available PDF/image tooling before writing. Do not rely only on abstract/introduction unless the PDF cannot be fully processed; state any limitation explicitly.

## Extraction Workflow

Use the helper script when useful:

```bash
python3 /Users/digoal/.codex/skills/paper-interpretation/scripts/extract_paper_assets.py INPUT_PDF_OR_URL --out .paper-work
```

The script creates:

- `paper.pdf` for the normalized PDF.
- `paper_text.md` with page-level text.
- `paper_tables.md` with table candidates when `pdfplumber` is available.
- `figures/` with extracted embedded images when `PyMuPDF` is available.
- `manifest.json` with extraction status and warnings.

Read the extracted files and inspect important figures/tables directly when they carry evidence, architecture, or results. If a library is unavailable, use other local tools if present; otherwise continue with the available extraction and mention the gap only if it affects confidence.

## Reading Checklist

Before writing, identify:

- Paper title, authors, venue/date when available.
- Research problem and practical motivation.
- Prior methods or baselines the paper contrasts against.
- Proposed method, system architecture, algorithm, data, or theory.
- Main experiments, metrics, datasets, tables, and figures.
- Claimed academic contributions and industrial implications.
- Assumptions, limitations, failure cases, and future work.

## Article Structure

Write in Chinese. Make the result accessible, but do not dilute technical substance.

### 1. 论文定位

Start by answering "这是什么、跟我有什么关系、值不值得读":

- Use 1-3 sentences to explain the real-world problem.
- State academic value: what gap it fills or what new capability/evidence it adds.
- State industrial value: where it can be used or what decision it can improve.
- Give one intuitive analogy tailored to the paper. Avoid reusing examples blindly; for a multi-agent finance paper, an analogy like "给 AI 配了一个完整的投资团队" is appropriate.

### 2. 前置知识地图

Build a prerequisite knowledge map:

```text
核心概念（必须懂） -> 支撑概念（有助于理解） -> 扩展概念（感兴趣再看）
```

For each important concept, explain with:

- A chart or structured list.
- An analogy.
- A concrete example.

Use Mermaid when it improves clarity:

```mermaid
flowchart LR
  A["核心概念"] --> B["支撑概念"]
  B --> C["扩展概念"]
```

### 3. 论文精读

Use the 5W1H frame and map it to the paper:

| 问题 | 对应论文结构 | 写作要求 |
|---|---|---|
| Why：为什么要做这个研究？ | Introduction / Motivation | 讲清痛点和旧方法不足 |
| What：提出了什么方法/系统？ | Method / Architecture | 用一句话先讲总方案 |
| How：具体怎么实现？ | Technical Details | 拆成模块、流程、公式或伪代码 |
| So What：结果怎么样？ | Experiments / Results | 引用关键表格/图/指标，解释数字意味着什么 |
| Now What：对我们意味着什么？ | Value / Discussion | 总结工业和学术启发 |

Prefer comparison over isolated explanation:

- Compare with prior methods or baselines.
- Compare with a reader's intuitive expectation.
- Explain what changes in the workflow, cost, accuracy, robustness, or scalability.

### 4. 术语解释

Include a glossary for important terms. Use this template:

```markdown
**Term（中文名）**
- 是什么：...
- 为什么重要：...
- 现实类比：...
```

Explain why the term is named that way when useful. Keep terms short and selective; prioritize terms required to understand the paper.

### 5. 批判性评估：论文强在哪里，边界在哪里

Evaluate, do not merely praise:

- Which assumptions must hold in real deployments?
- Are datasets, baselines, metrics, ablations, or statistical claims convincing?
- Where might the method fail?
- What cost, latency, safety, privacy, reproducibility, or integration risks exist?
- What future improvements are realistic?

Separate paper claims from your inference. Use wording like "论文证明了..." for supported claims and "可推断..." for reasoned extrapolation.

## Visual Requirements

Use Markdown-supported visuals at key points:

- Mermaid for process, architecture, concept maps, causal chains, and experiment flow.
- Markdown tables for comparisons, result interpretation, limitations, and term dictionaries.
- Simple SVG only when a static diagram is clearer than Mermaid.
- Text diagrams when they are more readable than formal charts.

Do not add decorative diagrams. Every visual must help explain a concept, method, result, or critique.

## Source Discipline

- Cite page numbers, section names, table numbers, or figure numbers whenever possible.
- Do not invent results, claims, datasets, or author intent.
- If extraction is incomplete, clearly label uncertain parts.
- Preserve important formulas or algorithms, but explain them in plain language.
- If the paper has supplementary material or appendices inside the PDF, include relevant evidence from them.

## Output Checklist

The final Markdown must include:

- Title.
- Paper metadata.
- 1-3 sentence overview.
- Academic value and industrial value.
- Knowledge map.
- Problem-solution-validation deep read.
- Key figure/table interpretations.
- Term glossary.
- Critical evaluation and future directions.
- References/source notes pointing back to paper sections, pages, figures, or tables.

After saving, report the absolute output path and any extraction limitations.
