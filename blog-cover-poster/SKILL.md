---
name: blog-cover-poster
description: Turn a blog post, article, notes, or any source material into a set of vertical poster images — one cover plus several coherent content slides that explain the core points. Renders HTML/CSS to exact-size PNGs via headless Chrome. Use whenever the user wants cover art, 讲解图/配图, carousel slides, 封面图, poster series, or "content images" from an article/文章/素材/文件, especially for blog, 公众号, 小红书, or social posts. Default output is 1080×1920 PNG named 1.png (cover), 2.png, 3.png … written to the current working directory (the project the user is in) — never the source file's directory.
---

# Blog Cover Poster

## Overview

Generate a **cover image** (`1.png`) plus **N coherent content slides** (`2.png`, `3.png`, …) from source material. Each image is an exact **1080×1920 PNG**. The pipeline authors one HTML file per page using bundled CSS/templates, then renders them to PNG with headless Chrome — this gives precise control over Chinese/English typography, color semantics, and emphasis.

## Workflow

1. **Read the source.** Take the file/text the user provides. Extract the title/hook and the core points. **Verify facts against the source only** — do not invent stats, names, or claims that aren't in the material.
2. **Plan the deck** (do this before writing any HTML):
   - Pick a **theme**: `theme-dark` (tech / AI / finance / dev topics) or `theme-light` (knowledge / tutorial / lifestyle / business explainer). Default to the topic fit; honor an explicit user request.
   - Decide **page count automatically** from the number of distinct core points: cover + one slide per point. Typical total is 4–8 images. Merge thin points; split overloaded ones. One idea per content slide.
   - Sketch a one-line outline: `1 cover → 2 <point> → 3 <point> …`. If the user gave a fixed count, follow it.
3. **Set up a scratch working dir** — author intermediate HTML/CSS here, **not** in the source directory and **not** littering the project dir:
   ```bash
   WORK=$(mktemp -d)
   cp <SKILL_DIR>/assets/poster.css "$WORK"/
   ```
   Author pages as `$WORK/page-1.html` (cover), `$WORK/page-2.html`, … using the templates as a starting point (see **Authoring pages**). The relative `<link href="poster.css">` resolves because the CSS sits beside them.
4. **Render PNGs into the current project directory** (`$PWD` — where the user invoked the skill), never the source file's directory:
   ```bash
   python3 <SKILL_DIR>/scripts/render.py --in "$WORK" --out "$PWD"
   ```
   This writes `1.png`, `2.png`, … (exact 1080×1920) into `$PWD`. `page-1.html` always becomes the cover `1.png`. If the user names a different output dir, use that instead — but default to `$PWD`.
5. **Inspect every PNG** with the Read tool. Check the checklist below. Fix the HTML in `$WORK` and re-render until clean.
6. **Clean up** the scratch dir (`rm -rf "$WORK"`). Only the `N.png` files remain in the project dir — that is the deliverable. The source directory is never touched.

## Authoring pages

Start from the templates and edit — don't write markup from scratch:
- `assets/template-cover.html` → `page-1.html`
- `assets/template-content.html` → `page-2.html`, `page-3.html`, …

Keep the same `theme-*` class on `<body>` across all pages.

### Content-slide layouts
The content template ships three layout blocks — **keep one per page, delete the rest**:
- **Points** (`ul.points`): 2–4 scannable items, best default for "reasons / steps / features".
- **Paragraph** (`.body`): 2–3 short sentences for a concept that needs prose.
- **Big stat** (`.stat`): one large number for a data point that deserves a full slide.

### Emphasis rules (semantic coloring & sizing)
Emphasis must track **meaning and importance**, not decoration:
- `.hl` / `.hl2` — filled color chip. **At most ONE per page**, on the single most important term. `.hl2` (warm) for contrast/warning/payoff; `.hl` (cool) otherwise.
- `.ul` — underline. Softer emphasis, for 1–2 secondary terms.
- `.accent` — colored text, for the **lead word** of each list item.
- `.muted` — de-emphasized text (subtitles, footers, labels).
- Type hierarchy is pre-tuned in the CSS: cover title 132px, content heading 84px, body 50–52px. Bigger = more important. If text overflows the 1920px height, **cut words or split into another slide — do not shrink below the template sizes**.

### Copywriting for posters
- Cover title: a punchy hook, ≤ ~14 CJK chars per line, ≤ 2 lines.
- Content headings: short, one idea. Content body: fragments over full paragraphs — these are read in seconds.
- Number the deck in the content `.index` (e.g. `01 / 05`) so the series reads as coherent.

## Verification checklist (per image)
- [ ] Size is exactly 1080×1920 (render.py enforces & prints this).
- [ ] No text is clipped at edges or overflows the bottom.
- [ ] Exactly one filled highlight chip per page, on the right term.
- [ ] Emphasis reflects the actual key point, not random words.
- [ ] Theme is consistent across all pages; contrast is readable.
- [ ] Content slides read as a coherent, ordered series (indices match count).
- [ ] Every claim traces to the source material.

## Notes
- `<SKILL_DIR>` is this skill's folder. `render.py` needs Python 3 with Pillow and a Chrome/Chromium install (it auto-detects common locations).
- To regenerate a single slide, edit its `page-N.html` and re-run render.py — it overwrites all `N.png` deterministically from the current HTML set.
- For custom fonts, brand colors, or logos: adjust `assets/poster.css` tokens (`--d-accent`, `--l-accent`, etc.) or add an `<img>` in the template.
