---
name: douban-book-notes
description: Generate a source-backed, shareable Chinese Markdown reading note from a Douban book URL. Use when the user provides a Douban book link and asks for 读书笔记, book notes, book summary, reading reflection, 图文并茂笔记, or a Markdown article that combines book metadata, high-quality external research, the author's argument, evidence, logic, assumptions, insights, transferability, and personal reflection saved under the current project's markdown directory.
---

# Douban Book Notes

## Goal

Create a rigorous, shareable Chinese reading note from one book's Douban URL. Treat the note as something the user can review personally, publish as an article, or explain aloud to others.

## Workflow

1. Parse the Douban URL and identify the exact book: title, author, translator if any, publisher, publication year, ISBN, original title, and edition caveats.
2. Search the web for high-quality materials about the book, author, historical context, interviews, reviews, lecture notes, academic or professional commentary, and official publisher information. Browse current sources; do not rely only on memory.
3. Keep only reliable materials. Prefer primary or near-primary sources: publisher pages, author interviews, official talks, academic reviews, serious media reviews, reputable book reviews, and high-signal long-form essays. Avoid low-effort summaries, unsourced listicles, scraped review farms, and anonymous content unless used only as weak sentiment context.
4. Read the book's public metadata and the selected materials. If the full book text is unavailable, state that limitation and avoid pretending to have read non-public chapters verbatim.
5. Load `references/note_framework.md` for the note structure, quality bar, and visual ideas.
6. Synthesize the final Markdown in Chinese unless the user explicitly asks for another language. Combine sourced facts, source-grounded interpretation, and your own clearly labeled thinking.
7. Save the Markdown under the current project's `markdown/` directory. Create the directory if missing. Use a filename like `YYYYMMDD-book-notes-<book-title-slug>.md`.

## Research Rules

- Use direct citations with links for important factual claims, publication metadata, author statements, statistics, historical claims, and controversial interpretations.
- Separate fact, source interpretation, and your own inference. Use wording such as "资料显示", "评论者认为", "我的判断是".
- Cross-check core metadata and claims across at least two sources when possible.
- Quote sparingly. Use short excerpts only when the wording itself matters; otherwise paraphrase and cite.
- If search results are thin, say so and write a more cautious note instead of padding.

## Required Output

The Markdown note must include:

- Title, book metadata, source list, and a short shareable abstract.
- Historical and intellectual context: what problem the book responds to, and why it mattered then and matters now.
- Author's central claims: distinguish main thesis, secondary claims, and implicit values.
- Evidence map: data, cases, stories, concepts, and authorities the author uses to support the claims.
- 1-3 condensed examples from the book: extract representative cases, scenes, stories, experiments, or examples that best carry the author's thinking. Keep them short, explain what each example proves, and avoid inventing details unavailable from the book or reliable sources.
- Logic map: how the argument moves from premises to conclusion.
- Assumption check: what must be true for the argument to hold, where it may fail, and what counterarguments matter.
- Thought reconstruction: what the author is really trying to change in the reader's perception or behavior.
- What I learned: concrete insights, not generic praise.
- Transfer and application: how to use the book's ideas in other domains, with examples.
- Reflection: agreement, disagreement, blind spots, and questions worth discussing.
- Share-ready section: a 3-5 minute talk track, discussion questions, and one-line takeaway.
- Visuals: include at least two useful visuals in Markdown, Mermaid, ASCII table, or inline SVG. Use visuals to explain structure, chronology, comparison, argument flow, or concept relationships.

## Quality Bar

- Be analytical, not a chapter-by-chapter digest.
- Make the author's logic visible enough that a reader can teach it to someone else.
- Do not overstate certainty. Call out uncertainty, missing evidence, and source limitations.
- Keep the prose publishable: clear section headings, dense but readable paragraphs, and no filler.
- End with a concise bibliography or source notes section.
