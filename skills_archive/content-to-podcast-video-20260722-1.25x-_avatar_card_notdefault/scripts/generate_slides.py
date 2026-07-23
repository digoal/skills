#!/usr/bin/env python3
"""
Slide Generator for the Content-to-Podcast-Video skill.

Renders 1080x1920 mobile slides (1.png, 2.png, ...) from a JSON spec, using
Headless Chrome. Every slide reserves a clean bottom 300px zone so burned-in
subtitles (42px) never overlap slide content.

Usage:
    python3 generate_slides.py --dir <out_dir> --spec <spec.json>

The spec is JSON: {"slides": [ <cover>, <content>, ... ]}

Cover slide:
    {"type": "cover",
     "kicker": "小标签 · 分隔用",
     "title": "主标题<br>可用 br 换行",
     "subtitle": "副标题，可多行",
     "badges": ["标签1", "标签2", "标签3"]}

Content slide (stats and cards are both optional):
    {"type": "content",
     "tag": "第一笔账 · 训练",
     "title": "标题，可用 <span class='hl'>高亮</span> 和 <br>",
     "note": "一句副说明",
     "stats": [{"big": "9.3万", "lbl": "MS1M 身份<br>510万张图"}],
     "cards": [{"style": "accent", "title": "卡片标题", "desc": "正文，可用 <b> 和 <span class='warn'>"}]}

Inline HTML allowed in text fields: <br>, <b>, <span class='hl'>, <span class='warn'>.
Card styles: accent (cyan) | purple | amber.
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

CSS = """
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  width: 1080px; height: 1920px;
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "PingFang SC", "Hiragino Sans GB", sans-serif;
  color: #F3F4F6; overflow: hidden; position: relative; background-color: #080B15;
}
.bg { position:absolute; inset:0; z-index:0;
  background:
    radial-gradient(circle at 20% 12%, rgba(6,182,212,0.20), transparent 42%),
    radial-gradient(circle at 85% 78%, rgba(139,92,246,0.20), transparent 45%),
    linear-gradient(160deg, #0A0E1A 0%, #080B15 60%, #0B1020 100%);
}
.grid { position:absolute; inset:0; z-index:0; opacity:0.05;
  background-image: linear-gradient(rgba(255,255,255,.6) 1px, transparent 1px),
                    linear-gradient(90deg, rgba(255,255,255,.6) 1px, transparent 1px);
  background-size: 70px 70px; }
/* Content wrap: reserve bottom 300px for subtitles */
.wrap { position:relative; z-index:1; width:100%; height:100%;
  padding: 90px 70px 300px 70px; display:flex; flex-direction:column; }
/* Cover wrap: centered, same bottom reserve */
.wrap-cover { position:relative; z-index:1; width:100%; height:100%;
  padding: 80px 70px 300px 70px; display:flex; flex-direction:column;
  justify-content:center; align-items:center; }

.kicker { font-size:30px; font-weight:800; letter-spacing:6px; color:#67E8F9;
  margin-bottom:40px; text-align:center; }
.cover-title { text-align:center; font-weight:900; color:#fff; line-height:1.22;
  max-width:960px; word-break:break-word;
  text-shadow: 0 6px 40px rgba(6,182,212,0.35); }
/* Adaptive cover sizes by line count */
.cover-title.l1 { font-size:140px; }
.cover-title.l2 { font-size:120px; }
.cover-title.l3 { font-size:88px; }
.cover-sub { margin-top:56px; font-size:38px; color:rgba(255,255,255,.62);
  text-align:center; font-weight:500; line-height:1.5; max-width:820px; }
.cover-badges { margin-top:70px; display:flex; gap:22px; flex-wrap:wrap; justify-content:center; }
.badge { padding:18px 34px; border-radius:50px; font-size:32px; font-weight:800;
  background:rgba(6,182,212,.12); border:2px solid rgba(6,182,212,.4); color:#7DD3FC; }

.sec-tag { display:inline-block; padding:12px 30px; border-radius:40px;
  background:rgba(6,182,212,.12); border:1.5px solid rgba(6,182,212,.35);
  color:#67E8F9; font-size:28px; font-weight:800; letter-spacing:3px;
  margin-bottom:34px; align-self:flex-start; }
.sec-title { font-size:70px; font-weight:900; color:#fff; line-height:1.15; margin-bottom:20px; }
.sec-title .hl { color:#67E8F9; }
.sec-note { font-size:34px; color:rgba(255,255,255,.55); line-height:1.45; margin-bottom:46px; }

.card { background:rgba(17,24,39,.72); border:1.5px solid rgba(255,255,255,.1);
  border-radius:28px; padding:40px 44px; margin-bottom:28px; }
.card.accent { border-left:8px solid #06B6D4; }
.card.purple { border-left:8px solid #8B5CF6; }
.card.amber  { border-left:8px solid #F59E0B; }
.card-title { font-size:44px; font-weight:800; color:#fff; margin-bottom:16px;
  display:flex; align-items:center; gap:18px; }
.card-desc { font-size:33px; color:rgba(255,255,255,.72); line-height:1.5; }
.card-desc b { color:#93C5FD; font-weight:800; }
.card-desc .warn { color:#FCD34D; font-weight:800; }

.stat-row { display:flex; gap:24px; margin-bottom:30px; }
.stat { flex:1; background:rgba(17,24,39,.72); border:1.5px solid rgba(255,255,255,.1);
  border-radius:24px; padding:34px 20px; text-align:center; }
.stat .big { font-size:60px; font-weight:900; color:#67E8F9; line-height:1; }
.stat .lbl { font-size:27px; color:rgba(255,255,255,.6); margin-top:14px; line-height:1.35; }
</style>
"""

def _page(inner, cover=False):
    w = "wrap-cover" if cover else "wrap"
    return (f"<!DOCTYPE html><html><head><meta charset='utf-8'>{CSS}</head>"
            f"<body><div class='bg'></div><div class='grid'></div>"
            f"<div class='{w}'>{inner}</div></body></html>")

def _build_cover(s):
    # Choose adaptive size class by number of <br>-delimited lines in the title.
    title = s.get("title", "")
    n_lines = title.count("<br>") + 1
    size_cls = {1: "l1", 2: "l2"}.get(n_lines, "l3")
    parts = []
    if s.get("kicker"):
        parts.append(f"<div class='kicker'>{s['kicker']}</div>")
    parts.append(f"<div class='cover-title {size_cls}'>{title}</div>")
    if s.get("subtitle"):
        parts.append(f"<div class='cover-sub'>{s['subtitle']}</div>")
    badges = s.get("badges") or []
    if badges:
        b = "".join(f"<div class='badge'>{x}</div>" for x in badges)
        parts.append(f"<div class='cover-badges'>{b}</div>")
    return _page("".join(parts), cover=True)

def _build_content(s):
    parts = []
    if s.get("tag"):
        parts.append(f"<div class='sec-tag'>{s['tag']}</div>")
    if s.get("title"):
        parts.append(f"<div class='sec-title'>{s['title']}</div>")
    if s.get("note"):
        parts.append(f"<div class='sec-note'>{s['note']}</div>")
    stats = s.get("stats") or []
    if stats:
        cells = "".join(
            f"<div class='stat'><div class='big'>{st.get('big','')}</div>"
            f"<div class='lbl'>{st.get('lbl','')}</div></div>" for st in stats)
        parts.append(f"<div class='stat-row'>{cells}</div>")
    for card in (s.get("cards") or []):
        style = card.get("style", "accent")
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
    ap = argparse.ArgumentParser(description="JSON-driven 1080x1920 slide generator")
    ap.add_argument("--dir", required=True, help="Output directory for 1.png..N.png")
    ap.add_argument("--spec", required=True, help="Path to slide spec JSON")
    args = ap.parse_args()
    if not os.path.exists(args.spec):
        print(f"❌ Spec file not found: {args.spec}")
        sys.exit(1)
    with open(args.spec, "r", encoding="utf-8") as f:
        spec = json.load(f)
    render_slides(spec, args.dir)

if __name__ == "__main__":
    main()
