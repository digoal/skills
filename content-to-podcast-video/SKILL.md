---
name: content-to-podcast-video
description: Converts long-form text or Markdown articles into mobile-optimized 1080x1920 presentation slides, single-speaker podcast audio with auto voice selection, synchronized subtitles, and a 1.25x speedup MP4 video. Use this skill when asked to create a video, slide deck + podcast, or short video from an article or document.
---

# Content to Podcast Video Pipeline

This skill automates the complete end-to-end pipeline for converting an article or text document into a vertical (1080x1920) mobile-optimized video featuring:
1. **Mobile Presentation Slides**: Large, readable vertical cards (1.png, 2.png, ...).
2. **Reserved Subtitle Area**: Bottom 280px of every slide image left blank/clean for larger subtitles.
3. **Host Portrait Overlay (Default)**: Embedded host card on the bottom-right (`digoal德哥` · `数据库 & AI 专家`), directly using pre-rendered `references/_avatar_card.png` by default.
4. **Single-Speaker Podcast**: Conversational script with domain-tailored TTS voice (default 1.25x speed `rate="+25%"`).
5. **Text-Authoritative Video Synthesis**: Content-driven slide image display (each image stays on screen exactly while its section is being spoken; no image looping) and high-precision TTS boundary-aligned ASS subtitles.

---

## Pipeline Architecture & Steps

### Step 1: Mobile Slide Generation (1080x1920)
- **Cover Slide (`1.png`)**:
  - Title **horizontally & vertically centered** on the cover.
  - **Adaptive font sizing based on title line count**:
    - 1 line: `font-size: 140px` (extra-large, maximum impact).
    - 2 lines: `font-size: 110px` (still large and bold).
    - 3 lines (only when title cannot be shortened): `font-size: 80px` (slightly smaller but still prominent).
  - **Title should be kept to 1–2 lines whenever possible**. Only use 3 lines when the title absolutely cannot be further condensed.
  - Use `text-align: center` and flexbox centering (`justify-content: center; align-items: center`).
  - High-impact mobile hero layout with bold gradients.
- **Content Slides (`2.png`, `3.png`, ...)**:
  - Section title (50–60px), body bullet points (28–34px).
  - High contrast glassmorphic cards.
- **Bottom Reserved Zone**:
  - Keep `padding-bottom: 300px` or `margin-bottom: 280px` on all slide containers.
  - **Do NOT place footers, text, or visual elements in the bottom 280px area**.
  - This extra-large reserved zone ensures the enlarged subtitles (42px) never overlap slide content.
- **Rendering**: Uses Headless Chrome (`--window-size=1080,1920 --screenshot=X.png`).

### Step 2: Podcast Script & Voice Selection
- **Script Adaptation**: Rewrites technical/long-form text into a natural 3–8 minute conversational single-speaker podcast script.
- **Slide Mapping Markers**: Insert explicit `[SLIDE: 1]`, `[SLIDE: 2]`, ... markers in `script.txt` corresponding to each generated slide image.
  ```text
  [SLIDE: 1]
  大家好，欢迎收听本期播客。本期我们要讨论的是分布式数据库体系架构。

  [SLIDE: 2]
  第一部分，存储与计算分离...

  [SLIDE: 3]
  第二部分，多版本并发控制...
  ```
- **Auto Voice Selection Matrix**:
  | Topic / Domain | Voice Code | Characteristics |
  | :--- | :--- | :--- |
  | Tech / Database / Architecture / Science | `zh-CN-YunjianNeural` | Male, authoritative, steady |
  | Business / Product / News | `zh-CN-YunxiNeural` | Male, energetic, natural |
  | Storytelling / Lifestyle / General | `zh-CN-XiaoxiaoNeural` | Female, warm, expressive |
  | Regional / Casual Discussion | `zh-CN-liaoning-XiaobeiNeural` | Female, lively |
- **Audio Generation**: Run `edge_tts` at **1.25x speed** (`rate="+25%"` by default).

### Step 3: High-Precision Subtitle Alignment & ASS Formatting
- **TTS Sentence Boundary Alignment (Zero Timing Drift)**:
  - Subtitle timestamps are captured directly from Microsoft Edge TTS engine boundary events (`SentenceBoundary`), eliminating premature or delayed subtitle cues.
  - Long sentences are sub-divided into balanced multi-line cues strictly within the exact sentence start and end boundaries.
- **Line Length & Formatting**:
  - Limit lines to max **14–16 Chinese characters** per line (to ensure text stays within 1080px with side margins).
  - Automatically break long clauses across **max 3 lines** (`\N`) when needed.
  - Two-line wrapping preferred; three-line only when content cannot fit in two.
  - Prevent splitting English words or punctuation pairs (`——`).
  - Both sides must have margin padding (MarginL/MarginR: 60px) to avoid text touching screen edges.
- **ASS Styling**:
  - `PlayResX: 1080`, `PlayResY: 1920`
  - `Fontname: Noto Sans CJK SC` (open-source OFL royalty-free font).
  - `Fontsize: 42` (enlarged for better readability on mobile).
  - `Alignment: 2` (Bottom Center).
  - `MarginL: 60`, `MarginR: 60` (side padding to keep text within safe area).
  - `MarginV: 100` (positioned in the bottom 280px reserved area).
  - `BorderStyle: 3`, `BackColour: &HA0080B15` (dark semi-transparent capsule box).

### Step 3.5: Host Portrait Card Overlay (Default: Enabled)

By default, every video **includes a host portrait card overlay** in the **bottom-right corner** of the video frame, sitting **inside the subtitle reserved zone** to the right of the subtitle text.

- **Default Avatar Card**: Directly uses pre-rendered `references/_avatar_card.png` (`digoal德哥` · `数据库 & AI 专家`), skipping dynamic synthesis for 0ms overhead.
  > 📌 **Path Resolution Note**: `references/_avatar_card.png` is a relative path inside the **skill base directory** (`<skill_dir>/references/_avatar_card.png`). When `build_video.py` is invoked from any arbitrary directory, it automatically resolves this path relative to the skill directory and copies the card into the current working directory, avoiding any "file not found" errors.
- **Card anatomy (420 × 220 px, RGBA transparent background):**
  - **Circular Avatar**: Center-cropped circular avatar with cyan glowing ring (`references/digoal.png`).
  - **Host Name**: Bold white text (`digoal德哥`).
  - **Host Title**: Cyan text (`数据库 & AI 专家`).
  - **Soundwave & LIVE Indicator**: Cyan waveform and pulse dot positioned cleanly in bottom-right corner without text overlap.
  - **Background**: Dark semi-transparent card (`#080B15`, 78% opacity) with cyan border.
- **Position in video:** `x=640, y=1410` (20px from right edge, inside the 280px bottom zone).
- **Customization / Dynamic Generation**: If `--avatar <path>` is passed with a custom photo, `build_video.py` dynamically invokes `scripts/make_avatar_overlay.py` to synthesize a new card overlay.
- **Disable Overlay**: Pass `--avatar none` if the overlay needs to be explicitly omitted.

### Step 4: Content-Driven Video Encoding (No Image Looping)
- **Content-Synchronized Slide Display**:
  - Images are **NOT looped**.
  - Each slide image (`1.png`, `2.png`, ...) is shown **only while speaking that specific page/section's content**.
  - Slide `i` stays on screen from the speech start of `[SLIDE: i]` until the speech start of `[SLIDE: i+1]` (the last slide remains visible until the podcast ends).
- **Audio Normalization & Muxing**: `-af "loudnorm" -max_muxing_queue_size 1024`.
- **FFmpeg Hardware Accelerated Encoding (Mac Videotoolbox)**:
  - With default host avatar card overlay (uses pre-rendered `references/_avatar_card.png` from skill directory or copied `_avatar_card.png` in output directory):
    ```bash
    ffmpeg -y -hwaccel videotoolbox \
      -f concat -safe 0 -i concat.txt \
      -i podcast.mp3 \
      -vf "fps=24,scale=1080:1920,format=yuv420p [base]; \
           movie='_avatar_card.png',format=rgba [ovrl]; \
           [base][ovrl] overlay=640:1410:eof_action=repeat [v_with_avatar]; \
           [v_with_avatar] subtitles='podcast.ass'" \
      -c:v h264_videotoolbox -b:v 2M -r 24 -tag:v avc1 \
      -c:a aac -ar 44100 -ac 2 -b:a 128k \
      -af "loudnorm" -max_muxing_queue_size 1024 -shortest -movflags +faststart output.mp4
    ```
- **Cross-Platform Software Fallback (Linux / Windows / Docker)**:
  - Uses `libx264 -preset veryfast -crf 20` for 8x–10x encoding speed on CPUs without hardware acceleration.

---

## HTML Article Illustrations (4:3 插图)

For inline article illustrations (插图), **NOT** `generate_slides.py`. Use the `html2png.js` script from wechat-publisher project.

### Critical: Hardcode CSS viewport to match target size

**The HTML body MUST match the target viewport exactly** — no `transform: scale()` tricks, no responsive breakpoints. Write CSS at the target size from the start.

```html
<!-- 4:3 插图: 1920×1440 -->
<body style="width:1920px; height:1440px; overflow:hidden; font-family:...">
```

### Rendering

```bash
node /root/new/src/wechat-publisher/scripts/html2png.js \
  --file /path/to/fig.html \
  --output /path/to/fig.png \
  --width 1920 --height 1440 --scale 1
```

- `--scale 1` = native resolution (no 2x upscaling)
- Output is exactly 1920×1440, no padding, no empty corners
- Average file size: 180–270KB per illustration
- For other ratios: adjust both CSS `body` size AND `--width/--height` to match

### Design guidelines for 4:3 article illustrations

- Title bar: 20% height, gradient header
- Content: use flexbox/grid, content determines internal proportions
- Dark background illustrations (深色背景): use `#0f172a` body bg
- Light background: use `#f8fafc` body bg
- Font sizes at 1920×1440: title 46–52px, body 24–30px
- Border radius: 16–24px for cards
- Gap between cards: 20–24px
- Side padding: 70px (≈3.6% of width)

### Cover illustration template

```html
<!-- 封面: 1920×1440, 深色科技风 -->
<body style="width:1920px; height:1440px; background:#0a0e1a; overflow:hidden;">
  <!-- 背景网格线 -->
  <div style="position:absolute;top:0;left:0;right:0;bottom:0;
    background-image:linear-gradient(rgba(99,102,241,0.08) 1px,transparent 1px),
                     linear-gradient(90deg,rgba(99,102,241,0.08) 1px,transparent 1px);
    background-size:80px 80px;"></div>

  <!-- 光晕装饰 -->
  <div style="position:absolute;top:-150px;right:-100px;width:600px;height:600px;
    background:rgba(99,102,241,0.25);filter:blur(120px);border-radius:50%;"></div>
  <div style="position:absolute;bottom:-100px;left:-80px;width:500px;height:500px;
    background:rgba(6,182,212,0.2);filter:blur(120px);border-radius:50%;"></div>

  <!-- 顶部标签 -->
  <div style="position:absolute;top:60px;left:50%;transform:translateX(-50%);
    background:rgba(99,102,241,0.2);border:1px solid rgba(99,102,241,0.4);
    border-radius:60px;padding:12px 32px;font-size:20px;color:#a5b4fc;font-weight:700;">
    小标签 · KEYWORD</div>

  <!-- 中心视觉元素（如插件架构图示 / 核心概念图） -->
  <!-- 位于视口正中，占 480×480px 区域 -->

  <!-- 底部标题区 -->
  <div style="position:absolute;bottom:100px;left:0;right:0;text-align:center;padding:0 200px;">
    <div style="font-size:80px;font-weight:900;
      background:linear-gradient(135deg,#e0e7ff 0%,#a5b4fc 50%,#06b6d4 100%);
      -webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:20px;">
      主标题
    </div>
    <div style="width:120px;height:4px;background:linear-gradient(90deg,#6366f1,#06b6d4);
      border-radius:2px;margin:0 auto 20px;"></div>
    <div style="font-size:28px;color:#64748b;">副标题 · 副标题</div>
  </div>
</body>
```

Key cover design elements:
- **Dark tech background** (`#0a0e1a`) with subtle grid lines
- **Glow orbs** (blurred circles, purple + cyan) for depth
- **Gradient title text** (white → indigo → cyan)
- **Center visual** (architecture diagram, concept illustration)
- **Minimal layout**: tag at top, visual center, title bottom

---

## Helper Automation Scripts

The skill provides two reusable Python scripts in `scripts/`:

1. `generate_slides.py`: Renders 1080x1920 slide PNGs (`1.png`..`N.png`) from a JSON spec.
   - `python3 scripts/generate_slides.py --dir <out_dir> --spec <spec.json>`
   - Auto-detects Chrome/Chromium/Edge; every slide keeps the bottom 300px subtitle zone clean.
2. `build_video.py`: TTS audio + high-precision ASS subtitles + default host portrait card overlay + content-driven non-looping subtitled MP4.
   - `python3 scripts/build_video.py --script-file <script.txt> [--dir <d>] [--slides N] [--topic tech] [--avatar <path>] [--host-name <name>] [--host-title <title>] [--output output.mp4]`
   - `--dir` defaults to the script file's directory (outputs land next to the script).
   - `--avatar`: Path to host avatar image or card. **Defaults to pre-rendered `references/_avatar_card.png`** (`digoal德哥`). Pass `none` to disable.
     - Note: `references/_avatar_card.png` is located inside the skill directory; `build_video.py` resolves relative paths to the skill root automatically when executed from other working directories.
   - `--host-name`: Display name of the host/speaker (default: `digoal德哥`).
   - `--host-title`: Title/intro line of the host (default: `数据库 & AI 专家`).
   - Automatically parses `[SLIDE: N]` markers in `script.txt` to calculate exact slide display durations.
   - Prechecks that `ffmpeg` is on PATH; falls back to `libx264` if `h264_videotoolbox` fails.

### Slide Spec JSON (for `generate_slides.py`)

> ⚠️ **CRITICAL JSON SYNTAX & QUOTE RULE**:
> - **NEVER use unescaped double quotes (`"`) inside JSON string values**.
> - **If content contains quotes, ALWAYS use Chinese brackets `「` and `」` instead of double quotes** (e.g. `"desc": "正文，包含「双引号内容」和 <span class='warn'>警示</span>"`).
> - This strictly prevents `json.JSONDecodeError` syntax crashes when generating slide specs.

```json
{
  "slides": [
    {"type": "cover", "kicker": "小标签", "title": "主标题<br>第二行",
     "subtitle": "副标题", "badges": ["标签1", "标签2", "标签3"]},
    {"type": "content", "tag": "第一笔账", "title": "标题 <span class='hl'>高亮</span>",
     "note": "一句说明",
     "stats": [{"big": "9.3万", "lbl": "标注<br>第二行"}],
     "cards": [{"style": "accent", "title": "卡片标题",
                "desc": "正文，可用 <b>强调</b> 和 <span class='warn'>警示</span>，引号请用「直角引号」"}]}
  ]
}
```

- Cover title font auto-sizes by `<br>` line count (1→140px, 2→120px, 3→88px). Keep it to 1–2 lines.
- Inline HTML allowed in text fields: `<br>`, `<b>`, `<span class='hl'>`, `<span class='warn'>`.
- Card `style`: `accent` (cyan) | `purple` | `amber`.

---

## Usage Instructions

When executing this skill:
1. Read the input document/markdown file.
2. Formulate 5–8 key slide topics and write a slide spec JSON + the single-speaker podcast script formatted with `[SLIDE: 1]`, `[SLIDE: 2]`, ... section tags.
   - **Check JSON validity**: Make sure all internal quotes inside JSON strings use `「` and `」` instead of `"`.
3. Choose the appropriate TTS voice based on topic (auto-selected by `build_video.py --topic`).
4. Generate slides: `python3 scripts/generate_slides.py --dir <d> --spec <spec.json>`.
5. **Build the video** (Host portrait overlay is **ENABLED BY DEFAULT** using pre-rendered `references/_avatar_card.png`):
   - Standard execution (with default `digoal德哥` avatar card):
     `python3 scripts/build_video.py --script-file <script.txt> --dir <d> --slides <N> --topic <t>`
   - With custom host card/avatar:
     `python3 scripts/build_video.py --script-file <script.txt> --dir <d> --slides <N> --topic <t> --avatar <photo.jpg> --host-name "姓名" --host-title "职位介绍"`
   - Disable host card:
     `python3 scripts/build_video.py --script-file <script.txt> --dir <d> --slides <N> --topic <t> --avatar none`
6. Verify outputs (`1.png`~`N.png`, `podcast.mp3`, `podcast.ass`, `output.mp4`). Inspect the video with `ffmpeg -i output.mp4`.

> [!TIP]
> The host portrait overlay is enabled by default using `references/_avatar_card.png`. Pass `--avatar none` to disable.

---

## Known Issues & Fix History

### 2026-08-08 Fixed: Blank slide PNGs under new Chrome

**Symptom**: `generate_slides.py` renders `1.png`..`N.png` with only the background gradient — no text or cards (~29KB each instead of 800KB+).

**Root cause** (Chrome 132+, especially 151): the script used the legacy `--headless` flag. In new headless mode its screenshot timing fires before content has painted, producing empty captures.

**Fix applied** (already in `scripts/generate_slides.py`; no action needed): use `--headless=new`. The absolute `file://` URI was already handled via `html_path.resolve().as_uri()`.

**⚠️ Warning**: do NOT add `--virtual-time-budget` to the render command while the slide CSS keeps the Google Fonts `@import` — the combination hangs Chrome indefinitely (tested: no output after 4 minutes).

**Verification**: rendered PNGs should be >800KB; blank ones are ~29KB. Optionally check the dark-text pixel ratio of the image.

### 2026-08-15 Fixed: FFmpeg Overlay Stall and Software Encoding Speedup on Linux / Cross-Platform

**Symptom**: `build_video.py` hangs at frame 0 (`0 fps` / `0.02x` speed) or throws `100 buffers queued in out_#0:0` and crashes with `moov atom not found` on Linux/ARM servers.

**Root cause**:
1. Single-frame image loaded via `movie='_avatar_card.png'` reached EOF, causing `overlay` to block waiting for new frames.
2. `libx264` default preset was `-preset medium`, which is slow on CPU software encoding.
3. `loudnorm` filter lookahead buffer caused muxer stall without `-max_muxing_queue_size 1024`.

**Fix applied** (in `scripts/build_video.py`):
1. Added `:eof_action=repeat` to the `overlay` filter (`overlay=640:1410:eof_action=repeat`).
2. Filter order adjusted: overlay avatar card first, then apply subtitles on top.
3. Software fallback upgraded to `-preset veryfast -crf 20 -max_muxing_queue_size 1024`, boosting encoding speed to **8x–10x (200+ fps)** while maintaining high quality and full macOS `videotoolbox` hardware acceleration compatibility.
