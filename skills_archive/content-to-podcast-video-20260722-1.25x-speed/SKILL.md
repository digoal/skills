---
name: content-to-podcast-video
description: Converts long-form text or Markdown articles into mobile-optimized 1080x1920 presentation slides, single-speaker podcast audio with auto voice selection, synchronized subtitles, and a 1.25x speedup MP4 video. Use this skill when asked to create a video, slide deck + podcast, or short video from an article or document.
---

# Content to Podcast Video Pipeline

This skill automates the complete end-to-end pipeline for converting an article or text document into a vertical (1080x1920) mobile-optimized video featuring:
1. **Mobile Presentation Slides**: Large, readable vertical cards (1.png, 2.png, ...).
2. **Reserved Subtitle Area**: Bottom 280px of every slide image left blank/clean for larger subtitles.
3. **Single-Speaker Podcast**: Conversational script with domain-tailored TTS voice (default 1.25x speed `rate="+25%"`).
4. **Text-Authoritative Video Synthesis**: Content-driven slide image display (each image stays on screen exactly while its section is being spoken; no image looping) and high-precision TTS boundary-aligned ASS subtitles.

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
  - `Fontsize: 42` (enlarged for better readability on mobile).
  - `Alignment: 2` (Bottom Center).
  - `MarginL: 60`, `MarginR: 60` (side padding to keep text within safe area).
  - `MarginV: 100` (positioned in the bottom 280px reserved area).
  - `BorderStyle: 3`, `BackColour: &HA0080B15` (dark semi-transparent capsule box).

### Step 4: Content-Driven Video Encoding (No Image Looping)
- **Content-Synchronized Slide Display**:
  - Images are **NOT looped**.
  - Each slide image (`1.png`, `2.png`, ...) is shown **only while speaking that specific page/section's content**.
  - Slide `i` stays on screen from the speech start of `[SLIDE: i]` until the speech start of `[SLIDE: i+1]` (the last slide remains visible until the podcast ends).
- **Audio Normalization**: `-af "loudnorm"`.
- **FFmpeg Hardware Accelerated Encoding (Mac Videotoolbox)**:
  ```bash
  ffmpeg -y -hwaccel videotoolbox \
    -f concat -safe 0 -i concat.txt \
    -i podcast.mp3 \
    -vf "fps=24,scale=1080:1920,format=yuv420p,subtitles=podcast.ass" \
    -c:v h264_videotoolbox -b:v 2M -r 24 -tag:v avc1 \
    -c:a aac -ar 44100 -ac 2 -b:a 128k \
    -af "loudnorm" \
    -shortest -movflags +faststart \
    output.mp4
  ```

---

## Helper Automation Scripts

The skill provides two reusable Python scripts in `scripts/`:

1. `generate_slides.py`: Renders 1080x1920 slide PNGs (`1.png`..`N.png`) from a JSON spec.
   - `python3 scripts/generate_slides.py --dir <out_dir> --spec <spec.json>`
   - Auto-detects Chrome/Chromium/Edge; every slide keeps the bottom 300px subtitle zone clean.
2. `build_video.py`: TTS audio + high-precision ASS subtitles + content-driven non-looping subtitled MP4.
   - `python3 scripts/build_video.py --script-file <script.txt> [--dir <d>] [--slides N] [--topic tech] [--output output.mp4]`
   - `--dir` defaults to the script file's directory (outputs land next to the script).
   - Automatically parses `[SLIDE: N]` markers in `script.txt` to calculate exact slide display durations.
   - Prechecks that `ffmpeg` is on PATH; falls back to `libx264` if `h264_videotoolbox` fails.

### Slide Spec JSON (for `generate_slides.py`)

```json
{
  "slides": [
    {"type": "cover", "kicker": "小标签", "title": "主标题<br>第二行",
     "subtitle": "副标题", "badges": ["标签1", "标签2", "标签3"]},
    {"type": "content", "tag": "第一笔账", "title": "标题 <span class='hl'>高亮</span>",
     "note": "一句说明",
     "stats": [{"big": "9.3万", "lbl": "标注<br>第二行"}],
     "cards": [{"style": "accent", "title": "卡片标题",
                "desc": "正文，可用 <b>强调</b> 和 <span class='warn'>警示</span>"}]}
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
3. Choose the appropriate TTS voice based on topic (auto-selected by `build_video.py --topic`).
4. Generate slides: `python3 scripts/generate_slides.py --dir <d> --spec <spec.json>`.
5. Build the video: `python3 scripts/build_video.py --script-file <script.txt> --dir <d> --slides <N> --topic <t>`.
6. Verify outputs (`1.png`~`N.png`, `podcast.mp3`, `podcast.ass`, `output.mp4`). Inspect the video with `ffmpeg -i output.mp4`.
