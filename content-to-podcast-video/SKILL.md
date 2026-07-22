---
name: content-to-podcast-video
description: Converts long-form text or Markdown articles into mobile-optimized 1080x1920 presentation slides, single-speaker podcast audio with auto voice selection, synchronized subtitles, and a 1.25x speedup MP4 video. Use this skill when asked to create a video, slide deck + podcast, or short video from an article or document.
---

# Content to Podcast Video Pipeline

This skill automates the complete end-to-end pipeline for converting an article or text document into a vertical (1080x1920) mobile-optimized video featuring:
1. **Mobile Presentation Slides**: Large, readable vertical cards (1.png, 2.png, ...).
2. **Reserved Subtitle Area**: Bottom 200px of every slide image left blank/clean.
3. **Single-Speaker Podcast**: Conversational script with domain-tailored TTS voice (normal speed 1.0x).
4. **1.25x Accelerated Video Synthesis**: Audio speedup (atempo=1.25), 3-second image looping, and perfectly synchronized burned-in ASS subtitles in the bottom reserved area.

---

## Pipeline Architecture & Steps

### Step 1: Mobile Slide Generation (1080x1920)
- **Cover Slide (`1.png`)**:
  - Extra-large main title (120–140px).
  - High-impact mobile hero layout with bold gradients.
- **Content Slides (`2.png`, `3.png`, ...)**:
  - Section title (50–60px), body bullet points (28–34px).
  - High contrast glassmorphic cards.
- **Bottom Reserved Zone**:
  - Keep `padding-bottom: 220px` or `margin-bottom: 200px` on all slide containers.
  - **Do NOT place footers, text, or visual elements in the bottom 200px area**.
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
- **Subtitles**: Extract raw timing using `edge_tts.SubMaker()`.

### Step 3: Subtitle Scaling & ASS Formatting
- **1.25x Speed Alignment**:
  - Divide all subtitle start and end timestamps by `1.25` (`ms_scaled = ms / 1.25`).
- **Line Length & Formatting**:
  - Limit lines to max 16–18 Chinese characters per line.
  - Automatically break long clauses across max 2 lines (`\N`).
  - Prevent splitting English words or punctuation pairs (`——`).
- **ASS Styling**:
  - `PlayResX: 1080`, `PlayResY: 1920`
  - `Fontsize: 32` (medium, perfectly legible on mobile without being intrusive).
  - `Alignment: 2` (Bottom Center).
  - `MarginV: 110` (centered in the bottom 200px reserved area).
  - `BorderStyle: 3`, `BackColour: &HA0080B15` (dark semi-transparent capsule box).

### Step 4: Video Encoding & Looping
- **Looping Mechanism**: Each slide displays for **3 seconds**, looping sequentially (`1.png -> 2.png -> ... -> N.png -> 1.png ...`) until the audio ends.
- **Audio Speedup & Normalization**: `-af "atempo=1.25,loudnorm"`.
- **FFmpeg Hardware Accelerated Encoding (Mac Videotoolbox)**:
  ```bash
  ffmpeg -y -hwaccel videotoolbox \
    -f concat -safe 0 -i concat.txt \
    -i podcast.mp3 \
    -vf "scale=1080:1920,format=yuv420p,subtitles=podcast.ass" \
    -c:v h264_videotoolbox -b:v 2M -r 24 -tag:v avc1 \
    -c:a aac -ar 44100 -ac 2 -b:a 128k \
    -af "atempo=1.25,loudnorm" \
    -shortest -movflags +faststart \
    output.mp4
  ```

---

## Helper Automation Scripts

The skill provides reusable Python automation scripts in `scripts/`:

1. `generate_slides.py`: Renders HTML slide templates into 1080x1920 PNG images.
2. `generate_podcast.py`: Converts text to TTS audio + ASS subtitles with 1.25x time scaling.
3. `build_video.py`: Runs the complete pipeline automatically.

---

## Usage Instructions

When executing this skill:
1. Read the input document/markdown file.
2. Formulate 5–8 key slide topics and write the single-speaker podcast script.
3. Choose the appropriate TTS voice based on topic.
4. Execute `python3 scripts/build_video.py --input <file_path>` or run the step-by-step pipeline.
5. Verify output files (`1.png`~`N.png`, `podcast.mp3`, `podcast.ass`, `output.mp4`).
