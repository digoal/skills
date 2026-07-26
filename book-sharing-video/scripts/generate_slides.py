#!/usr/bin/env python3
"""
Slide Generator for the Book-Sharing-Video skill.

Renders 1080x1920 warm book-style slides (1.png, 2.png, ...) from a JSON spec,
using Headless Chrome. Every slide reserves a clean bottom 300px zone so
burned-in subtitles never overlap slide content.

Visual style: Warm book-reading theme — cream/beige background, brown/amber accents,
paper texture feel. NOT the dark cyberpunk tech style.

Usage:
    python3 generate_slides.py --dir <out_dir> --spec <spec.json>

Cover slide:
    {"type": "cover",
     "kicker": "读书分享",
     "title": "书名<br>第二行",
     "author": "作者名",
     "subtitle": "一句话推荐语",
     "badges": ["标签1", "标签2"]}

Content slide:
    {"type": "content",
     "tag": "核心观点一",
     "title": "标题",
     "note": "一句副说明",
     "stats": [{"big": "95%", "lbl": "读者好评"}],
     "cards": [{"style": "warm", "title": "卡片标题", "desc": "正文"}]}

Card styles: warm (amber) | earth (brown) | sage (muted green)
Inline HTML: <br>, <b>, <span class='hl'>, <span class='quote'>
"""

import os
import sys
import json
import shutil
import argparse
import subprocess

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    shutil.which("google-chrome"),
    shutil.which("google-chrome-stable"),
    shutil.which("chromium"),
    shutil.which("chromium-browser"),
]

def find_chrome():
    for c in CHROME_CANDIDATES:
        if c and os.path.exists(c):
            return c
    return None

# ─── Warm Book-Style CSS ────────────────────────────────────────────────
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;700;900&family=Noto+Sans+SC:wght@400;500;700;900&display=swap');

* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  width: 1080px; height: 1920px;
  font-family: "Noto Sans SC", "Noto Sans CJK SC", "Source Han Sans SC",
               "PingFang SC", "Hiragino Sans GB", system-ui, sans-serif;
  color: #3D2B1F; overflow: hidden; position: relative;
  background-color: #FAF6F0;
}

/* Warm background with subtle paper texture */
.bg {
  position: absolute; inset: 0; z-index: 0;
  background:
    radial-gradient(ellipse at 25% 15%, rgba(210,160,90,0.15), transparent 50%),
    radial-gradient(ellipse at 80% 85%, rgba(180,120,60,0.10), transparent 50%),
    linear-gradient(170deg, #FDF8F0 0%, #FAF6F0 40%, #F5EDE0 100%);
}

/* Subtle paper grain texture via CSS noise */
.grain {
  position: absolute; inset: 0; z-index: 0; opacity: 0.03;
  background-image:
    repeating-linear-gradient(0deg, rgba(139,90,43,0.15) 0px, transparent 1px, transparent 3px),
    repeating-linear-gradient(90deg, rgba(139,90,43,0.10) 0px, transparent 1px, transparent 5px);
}

/* Decorative book-like elements */
.deco-line {
  position: absolute; z-index: 0;
  width: 2px; background: linear-gradient(to bottom, transparent, rgba(180,130,70,0.2), transparent);
}
.deco-line.left { left: 50px; top: 80px; height: calc(100% - 380px); }
.deco-line.right { right: 50px; top: 80px; height: calc(100% - 380px); }

/* Content wrap: reserve bottom 300px for subtitles */
.wrap {
  position: relative; z-index: 1; width: 100%; height: 100%;
  padding: 100px 80px 300px 80px; display: flex; flex-direction: column;
}

/* Cover wrap: centered, same bottom reserve */
.wrap-cover {
  position: relative; z-index: 1; width: 100%; height: 100%;
  padding: 120px 80px 300px 80px; display: flex; flex-direction: column;
  justify-content: center; align-items: center;
}

/* ── Cover Styles ── */
.kicker {
  font-size: 28px; font-weight: 700; letter-spacing: 8px;
  color: #B07D3A; margin-bottom: 50px; text-align: center;
  text-transform: uppercase;
  border: 2px solid rgba(176,125,58,0.3);
  padding: 12px 36px; border-radius: 30px;
  background: rgba(176,125,58,0.06);
}
.cover-title {
  text-align: center; font-weight: 900; color: #2C1810;
  line-height: 1.25; max-width: 900px; word-break: break-word;
  font-family: "Noto Serif SC", "Source Han Serif SC", "STSong", serif;
}
/* Adaptive cover sizes by line count */
.cover-title.l1 { font-size: 120px; }
.cover-title.l2 { font-size: 90px; }
.cover-title.l3 { font-size: 70px; }

.cover-author {
  margin-top: 40px; font-size: 36px; color: #8B6A4F;
  text-align: center; font-weight: 500; letter-spacing: 4px;
}
.cover-sub {
  margin-top: 50px; font-size: 34px; color: rgba(60,43,31,0.55);
  text-align: center; font-weight: 400; line-height: 1.6; max-width: 780px;
  font-style: italic;
}
.cover-divider {
  width: 120px; height: 3px; background: linear-gradient(to right, transparent, #C49A5C, transparent);
  margin: 40px auto;
}
.cover-badges {
  margin-top: 50px; display: flex; gap: 20px; flex-wrap: wrap; justify-content: center;
}
.badge {
  padding: 14px 30px; border-radius: 40px; font-size: 28px; font-weight: 700;
  background: rgba(176,125,58,0.08); border: 1.5px solid rgba(176,125,58,0.25);
  color: #9C7A4F;
}

/* Book icon decoration on cover */
.cover-icon {
  margin-top: 60px; opacity: 0.15; text-align: center;
}
.cover-icon svg { width: 80px; height: 80px; }

/* ── Content Slide Styles ── */
.sec-tag {
  display: inline-block; padding: 10px 28px; border-radius: 30px;
  background: rgba(192,130,50,0.10); border: 1.5px solid rgba(192,130,50,0.25);
  color: #B07D3A; font-size: 26px; font-weight: 700; letter-spacing: 3px;
  margin-bottom: 30px; align-self: flex-start;
}
.sec-title {
  font-size: 56px; font-weight: 900; color: #2C1810; line-height: 1.2;
  margin-bottom: 18px;
  font-family: "Noto Serif SC", "Source Han Serif SC", "STSong", serif;
}
.sec-title .hl { color: #B07D3A; }
.sec-note {
  font-size: 30px; color: rgba(60,43,31,0.50); line-height: 1.5;
  margin-bottom: 40px; font-style: italic;
}

/* Cards */
.card {
  background: rgba(255,252,247,0.85); border: 1.5px solid rgba(180,140,80,0.15);
  border-radius: 24px; padding: 36px 40px; margin-bottom: 24px;
  box-shadow: 0 4px 20px rgba(139,90,43,0.06);
}
.card.warm  { border-left: 7px solid #D4A04A; }
.card.earth { border-left: 7px solid #8B6A4F; }
.card.sage  { border-left: 7px solid #7A9B6D; }
.card-title {
  font-size: 38px; font-weight: 800; color: #2C1810; margin-bottom: 14px;
  display: flex; align-items: center; gap: 14px;
}
.card-desc {
  font-size: 30px; color: rgba(60,43,31,0.72); line-height: 1.6;
}
.card-desc b { color: #8B5A2B; font-weight: 800; }
.card-desc .quote {
  color: #B07D3A; font-style: italic; font-weight: 600;
  border-left: 3px solid #D4A04A; padding-left: 12px;
  display: inline;
}
.card-desc .warn { color: #C4553A; font-weight: 700; }

/* Stats row */
.stat-row { display: flex; gap: 20px; margin-bottom: 28px; }
.stat {
  flex: 1; background: rgba(255,252,247,0.85);
  border: 1.5px solid rgba(180,140,80,0.15);
  border-radius: 20px; padding: 30px 18px; text-align: center;
  box-shadow: 0 4px 16px rgba(139,90,43,0.05);
}
.stat .big {
  font-size: 52px; font-weight: 900; color: #B07D3A; line-height: 1;
  font-family: "Noto Serif SC", serif;
}
.stat .lbl {
  font-size: 24px; color: rgba(60,43,31,0.55); margin-top: 12px; line-height: 1.35;
}

/* Quote block for content slides */
.quote-block {
  background: rgba(210,160,90,0.08); border-left: 5px solid #C49A5C;
  border-radius: 0 16px 16px 0; padding: 28px 32px; margin-bottom: 24px;
  font-size: 32px; color: #5C3D1E; font-style: italic; line-height: 1.6;
  font-family: "Noto Serif SC", serif;
}
</style>
"""

def _page(inner, cover=False):
    w = "wrap-cover" if cover else "wrap"
    return (f"<!DOCTYPE html><html><head><meta charset='utf-8'>{CSS}</head>"
            f"<body><div class='bg'></div><div class='grain'></div>"
            f"<div class='deco-line left'></div><div class='deco-line right'></div>"
            f"<div class='{w}'>{inner}</div></body></html>")

def _build_cover(s):
    title = s.get("title", "")
    n_lines = title.count("<br>") + 1
    size_cls = {1: "l1", 2: "l2"}.get(n_lines, "l3")
    parts = []
    if s.get("kicker"):
        parts.append(f"<div class='kicker'>{s['kicker']}</div>")
    parts.append(f"<div class='cover-title {size_cls}'>{title}</div>")
    if s.get("author"):
        parts.append(f"<div class='cover-author'>{s['author']}</div>")
    parts.append("<div class='cover-divider'></div>")
    if s.get("subtitle"):
        parts.append(f"<div class='cover-sub'>{s['subtitle']}</div>")
    badges = s.get("badges") or []
    if badges:
        b = "".join(f"<div class='badge'>{x}</div>" for x in badges)
        parts.append(f"<div class='cover-badges'>{b}</div>")
    # Book icon decoration
    parts.append("""<div class='cover-icon'>
        <svg viewBox='0 0 80 80' fill='none' xmlns='http://www.w3.org/2000/svg'>
            <path d='M15 12 C15 12 40 8 40 8 L40 68 C40 68 15 72 15 72 Z' fill='#8B6A4F' opacity='0.4'/>
            <path d='M65 12 C65 12 40 8 40 8 L40 68 C40 68 65 72 65 72 Z' fill='#A0845C' opacity='0.3'/>
            <path d='M40 8 L40 68' stroke='#6B4F3A' stroke-width='1.5' opacity='0.3'/>
        </svg>
    </div>""")
    return _page("".join(parts), cover=True)

def _build_content(s):
    parts = []
    if s.get("tag"):
        parts.append(f"<div class='sec-tag'>{s['tag']}</div>")
    if s.get("title"):
        parts.append(f"<div class='sec-title'>{s['title']}</div>")
    if s.get("note"):
        parts.append(f"<div class='sec-note'>{s['note']}</div>")
    # Quote block (optional)
    if s.get("quote"):
        parts.append(f"<div class='quote-block'>「{s['quote']}」</div>")
    stats = s.get("stats") or []
    if stats:
        cells = "".join(
            f"<div class='stat'><div class='big'>{st.get('big','')}</div>"
            f"<div class='lbl'>{st.get('lbl','')}</div></div>" for st in stats)
        parts.append(f"<div class='stat-row'>{cells}</div>")
    for card in (s.get("cards") or []):
        style = card.get("style", "warm")
        title_html = f"<div class='card-title'>{card['title']}</div>" if card.get("title") else ""
        parts.append(f"<div class='card {style}'>{title_html}"
                     f"<div class='card-desc'>{card.get('desc','')}</div></div>")
    return _page("".join(parts), cover=False)

def build_slide_html(slide):
    return _build_cover(slide) if slide.get("type") == "cover" else _build_content(slide)

def render_slides(spec, out_dir, chrome=None):
    chrome = chrome or find_chrome()
    if not chrome:
        print("❌ Chrome/Chromium not found. Install Google Chrome or set the path.")
        sys.exit(1)
    slides = spec["slides"] if isinstance(spec, dict) else spec
    os.makedirs(out_dir, exist_ok=True)
    ok = 0
    for i, slide in enumerate(slides, 1):
        png = os.path.join(out_dir, f"{i}.png")
        html = os.path.join(out_dir, f"_slide_{i}.html")
        with open(html, "w", encoding="utf-8") as f:
            f.write(build_slide_html(slide))
        subprocess.run([
            chrome, "--headless", f"--screenshot={png}",
            "--window-size=1080,1920", "--hide-scrollbars",
            "--default-background-color=00000000", f"file://{html}"
        ], capture_output=True, text=True)
        os.remove(html)
        good = os.path.exists(png)
        ok += good
        print(f"  {'✓' if good else '✗'} {i}.png")
    print(f"Rendered {ok}/{len(slides)} slides -> {out_dir}")
    return ok

def main():
    ap = argparse.ArgumentParser(description="JSON-driven 1080x1920 warm book-style slide generator")
    ap.add_argument("--dir", required=True, help="Output directory for 1.png..N.png")
    ap.add_argument("--spec", required=True, help="Path to slide spec JSON")
    args = ap.parse_args()
    if not os.path.exists(args.spec):
        print(f"❌ Spec file not found: {args.spec}")
        sys.exit(1)
    try:
        with open(args.spec, "r", encoding="utf-8") as f:
            spec = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ JSON parsing error in spec file '{args.spec}': {e}")
        print("  💡 Tip: Ensure internal double quotes in text/titles are replaced with Chinese brackets 「 and 」.")
        sys.exit(1)
    render_slides(spec, args.dir)

if __name__ == "__main__":
    main()
