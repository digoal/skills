---
name: open-source-project-article
description: Analyze an open-source project from a repository URL and write a deeply sourced Chinese Markdown article. Use when the user asks to research a GitHub/open-source project, read its README, use DeepWiki MCP for architecture analysis, search related articles, compare competitors, validate claims, and save the final article under the current project's markdown directory.
---

# Open Source Project Article

Use this skill to turn an open-source project URL into an evidence-grounded, article-ready Chinese Markdown file.

## Non-Negotiable Source Order

Always gather evidence in this exact order:

1. Fetch and read the project `README.md` or `readme.md`.
2. Use DeepWiki MCP to analyze the repository architecture.
3. Identify and ask necessary clarification questions, only when they materially affect article direction, audience, or output location. If not blocked, state assumptions and continue.
4. Search the web for related articles, docs, benchmarks, releases, comparisons, and case studies.
5. Only then draft the article.

Do not start with web search. Do not write from memory. Do not skip DeepWiki when the repository is supported by DeepWiki MCP.

## Inputs

Require a repository URL or `owner/repo`. If the user omits it, ask for it.

Infer defaults unless risky:

- Article language: Chinese.
- Output location: `markdown/` under the current project directory.
- File name: repository name normalized to lowercase hyphen-case, e.g. `pg-wait-tracer.md`.
- Article audience: DBA, architect, developer, technical decision maker.

Create `markdown/` if missing.

## Evidence Workflow

1. Normalize the repository:
   - Convert GitHub URL to `owner/repo`.
   - Preserve the original URL for citations.
2. Fetch README:
   - Prefer repository files or GitHub raw content.
   - Read `README.md`; if absent, try `readme.md`.
   - If README cannot be fetched, stop and report what was attempted.
3. Ask DeepWiki:
   - Use `mcp__deepwiki__read_wiki_structure` first when available.
   - Use `mcp__deepwiki__ask_question` for architecture, core modules, data flow, extension points, tradeoffs, tests, and limitations.
   - Treat DeepWiki as architecture evidence, not as a substitute for README or code.
4. Ask necessary questions:
   - Ask only if the answer changes the article materially, such as target audience, article style, competitor set, or whether to emphasize hands-on deployment vs strategic evaluation.
   - In default mode, avoid blocking on preferences; state reasonable assumptions and proceed.
5. Search web:
   - Use primary sources first: official docs, repository docs, release notes, papers, benchmark reports, vendor docs.
   - Use secondary articles only to understand ecosystem interpretation or adoption cases.
   - For current project status, releases, stars, or ecosystem facts, verify live.
6. Build an evidence pack:
   - README facts.
   - DeepWiki architecture findings.
   - Official or primary-source facts.
   - Benchmarks/data/cases with source links.
   - Competitor facts with source links.
   - Uncertainties and assumptions.

## Article Requirements

Read `references/article-structure.md` before drafting. Use it as the mandatory content checklist.

The article must include:

- Clear thesis, not neutral feature listing.
- Preconditions for the thesis to hold.
- Alternative thesis or recommendation when those preconditions collapse.
- Authoritative data or cases supporting the assumptions.
- Authoritative data or cases supporting the thesis.
- Background.
- Scenario introduction.
- Pain point analysis.
- Sharp critique of traditional solutions.
- Product solution.
- Product principles and architecture.
- Before/after effect comparison.
- Competitor comparison.
- Usage scenarios.
- Best practices.
- Hands-on steps.
- Risks, limitations, and failure conditions.

For every major thesis, include this logic explicitly:

```text
观点：...
成立前提：...
支撑证据：...
如果前提崩塌：应转向的其他观点/方案是...
```

Insert Mermaid or SVG diagrams at every core argument section. Prefer Mermaid unless SVG is clearly better. Diagrams must explain, not decorate.

## Validation

Read `references/validation-checklist.md` before finalizing.

Validate:

- Source order was followed.
- Claims map to sources or are clearly marked as inference.
- Data, cases, and benchmarks are quoted with context and limitations.
- Competitor comparison is fair and sourced.
- The article states what alternative viewpoint or product recommendation follows if core assumptions fail.
- Hands-on commands match README/docs.
- Mermaid syntax is plausible.
- Output path is `markdown/<slug>.md`.

If validation finds weak evidence, revise the article before saving. If evidence remains unavailable, state the gap inside the article instead of inventing support.

## Output

Save the article to:

```text
<current-project>/markdown/<repo-slug>.md
```

After saving, report:

- File path.
- Evidence sources used.
- Any unresolved evidence gaps.
- Validation summary.
