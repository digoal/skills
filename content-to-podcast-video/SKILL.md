---
name: content-to-podcast-video
description: Converts long-form text or Markdown articles into mobile-optimized 1080x1920 presentation slides, single-speaker podcast audio with auto voice selection, synchronized subtitles, and a 1.25x speedup MP4 video. Use this skill when asked to create a video, slide deck + podcast, or short video from an article or document.
---

# Content to Podcast Video Pipeline

This skill automates the complete end-to-end pipeline for converting an article or text document into a vertical (1080x1920) mobile-optimized video featuring:
1. **Mobile Presentation Slides**: Large, readable vertical cards (1.png, 2.png, ...).
2. **Reserved Subtitle Area**: Bottom 280px of every slide image left blank/clean for larger subtitles.
3. **Single-Speaker Podcast**: Conversational script with domain-tailored TTS voice (normal speed 1.0x).
4. **Text-Authoritative Video Synthesis**: 1.0x normal speed, 6-second image looping (configurable via `--seconds`), and 100% complete, perfectly synchronized burned-in ASS subtitles in the bottom reserved area.

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
- **Auto Voice Selection Matrix**:
  | Topic / Domain | Voice Code | Characteristics |
  | :--- | :--- | :--- |
  | Tech / Database / Architecture / Science | `zh-CN-YunjianNeural` | Male, authoritative, steady |
  | Business / Product / News | `zh-CN-YunxiNeural` | Male, energetic, natural |
  | Storytelling / Lifestyle / General | `zh-CN-XiaoxiaoNeural` | Female, warm, expressive |
  | Regional / Casual Discussion | `zh-CN-liaoning-XiaobeiNeural` | Female, lively |
- **Audio Generation**: Run `edge_tts` at **1.0x normal speed** (`rate="+0%"`).

### Step 3: Text-Authoritative Subtitle Time Alignment & ASS Formatting
- **100% Text-Authoritative Coverage (Zero Missing Characters)**:
  - Sentences are extracted directly from the podcast script as the absolute source of truth.
  - Every single character from start to end is included in the subtitle cues.
- **Syllable-Weighted Time Alignment (Zero Audio Drift)**:
  - Audio duration is probed directly from the generated MP3 file.
  - Timestamps are dynamically mapped across the exact audio timeline based on phonetic reading weights and punctuation pause factors.
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

### Step 4: Video Encoding & Looping
- **Looping Mechanism**: Each slide displays for **N seconds** (default 6, set via `--seconds`), looping sequentially (`1.png -> 2.png -> ... -> N.png -> 1.png ...`) until the audio ends. Loop count auto-scales to outlast the audio; `-shortest` trims the tail.
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
2. `build_video.py`: TTS audio + text-authoritative ASS subtitles + looped, subtitled MP4.
   - `python3 scripts/build_video.py --script-file <script.txt> [--dir <d>] [--slides N] [--topic tech] [--seconds 6] [--output output.mp4]`
   - `--dir` defaults to the script file's directory (outputs land next to the script).
   - `--seconds` sets how long each slide stays on screen (default 6). Subtitles are timed to the audio, not the slides, and the loop count auto-scales, with `-shortest` trimming any excess tail.
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
2. Formulate 5–8 key slide topics and write a slide spec JSON + the single-speaker podcast script.
3. Choose the appropriate TTS voice based on topic (auto-selected by `build_video.py --topic`).
4. Generate slides: `python3 scripts/generate_slides.py --dir <d> --spec <spec.json>`.
5. Build the video: `python3 scripts/build_video.py --script-file <script.txt> --dir <d> --slides <N> --topic <t>`.
6. Verify outputs (`1.png`~`N.png`, `podcast.mp3`, `podcast.ass`, `output.mp4`). Inspect the
   video with `ffmpeg -i output.mp4` (ffprobe is not required).
