# Validation Checklist

Run this checklist before saving the final article.

## Source Order

- README/readme was fetched and read before any other source.
- DeepWiki MCP architecture analysis was performed after README.
- Clarifying questions were asked only if necessary, or assumptions were stated.
- Web search came after README and DeepWiki.
- Primary sources were prioritized over secondary commentary.

## Evidence Integrity

- Every core product capability is supported by README, docs, code, or DeepWiki.
- Every architecture claim is supported by DeepWiki, code/docs, or clearly labeled inference.
- Every performance number, benchmark, adoption claim, market claim, or release fact has a source and date/context.
- Competitor claims cite official docs or primary sources.
- No source is over-quoted; paraphrase unless a short quote is essential.
- Unavailable evidence is explicitly called out rather than filled in.

## Logic

- The thesis is explicit.
- The assumptions for the thesis are explicit.
- There is evidence supporting the assumptions.
- There is evidence supporting the thesis.
- The article explains what conclusion follows if each core assumption collapses.
- The alternative conclusion is concrete: competitor, traditional solution, do-not-adopt recommendation, or research-only positioning.
- Traditional solutions are critiqued through concrete failure modes.
- The product solution directly addresses the listed pain points.
- Before/after comparison does not claim unsourced performance gains.
- Competitor comparison uses comparable dimensions.
- Risks and limitations can change the recommendation.

## Hands-On Correctness

- Install commands match README/docs.
- Config names, environment variables, SQL functions, ports, flags, and file paths match sources.
- Verification commands prove that the setup works.
- Rollback or cleanup path is included when relevant.
- Commands that require privileges say so.

## Markdown Output

- Output is saved under `markdown/<repo-slug>.md` in the current project.
- Markdown headings are clean.
- Mermaid code fences use `mermaid`.
- Mermaid diagrams have valid-looking syntax.
- Tables are readable.
- Source links are included in a final references section.
