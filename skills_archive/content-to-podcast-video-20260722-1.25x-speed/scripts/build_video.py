#!/usr/bin/env python3
"""
Content to Podcast Video Generator
Automates: Slide HTML/PNG generation -> TTS Audio (1.0x normal speed) -> Text-Authoritative ASS Subtitles -> MP4 Video
"""

import os
import sys
import re
import shutil
import argparse
import subprocess
import asyncio
import edge_tts

# Voice selection table based on content topic
VOICE_MAP = {
    "tech": "zh-CN-YunjianNeural",        # Tech, DB, Architecture, Code
    "business": "zh-CN-YunxiNeural",     # Business, Finance, News, Product
    "story": "zh-CN-XiaoxiaoNeural",     # Story, Lifestyle, Emotion, General
    "casual": "zh-CN-liaoning-XiaobeiNeural" # Regional, Casual
}

def auto_select_voice(topic_hint, text_content):
    if topic_hint in VOICE_MAP:
        return VOICE_MAP[topic_hint]
    
    text_lower = text_content.lower()
    if any(k in text_lower for k in ["数据库", "olap", "架构", "代码", "sql", "算法", "系统", "引擎", "ai", "开源"]):
        return VOICE_MAP["tech"]
    elif any(k in text_lower for k in ["商业", "融资", "市场", "增长", "经济", "企业", "公司", "战略"]):
        return VOICE_MAP["business"]
    elif any(k in text_lower for k in ["故事", "生活", "情感", "健康", "心理", "电影", "体验"]):
        return VOICE_MAP["story"]
    else:
        return VOICE_MAP["tech"]

def ms_to_ass(ms):
    s, ms = divmod(int(max(0, ms)), 1000)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    cs = ms // 10
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def get_audio_duration_ms(audio_file):
    """Probes exact audio duration in milliseconds using ffmpeg."""
    cmd = ["ffmpeg", "-i", audio_file]
    res = subprocess.run(cmd, capture_output=True, text=True)
    for line in res.stderr.splitlines():
        if "Duration:" in line:
            m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", line)
            if m:
                h, mins, secs = m.groups()
                return (int(h) * 3600 + int(mins) * 60 + float(secs)) * 1000
    return 0.0

def calc_text_weight(text):
    """Calculates phonetic/reading duration weight for a given text snippet."""
    weight = 0.0
    cjk_count = len(re.findall(r'[\u4e00-\u9fa5]', text))
    weight += cjk_count * 1.0
    eng_words = re.findall(r'[a-zA-Z0-9]+', text)
    weight += len(eng_words) * 1.2
    pauses_major = len(re.findall(r'[。！？\n]', text))
    pauses_minor = len(re.findall(r'[，；：,;:]', text))
    weight += pauses_major * 1.5 + pauses_minor * 0.8
    return max(0.5, weight)

def smart_format_subtitle(text, max_line_len=15):
    """
    Formats subtitle text into 1-3 lines separated by \\N.
    Breaks cleanly at spaces, punctuation, or CJK boundaries without breaking English words in half.
    Strips trailing periods for cleaner visual output on mobile slides.
    """
    text = text.strip().rstrip("。")
    if not text:
        return ""
    
    if len(text) <= max_line_len:
        return text

    tokens = []
    curr_token = ""
    for char in text:
        if ord(char) > 0x2FFF or char in ' \t\n,.:;!?，。！？；、':
            if curr_token:
                tokens.append(curr_token)
                curr_token = ""
            tokens.append(char)
        else:
            curr_token += char
    if curr_token:
        tokens.append(curr_token)

    lines = []
    curr_line = ""
    for tok in tokens:
        if len(curr_line) + len(tok) <= max_line_len:
            curr_line += tok
        else:
            if curr_line:
                lines.append(curr_line.strip())
            curr_line = tok.lstrip()
    if curr_line:
        lines.append(curr_line.strip())

    if len(lines) > 3:
        l1 = ' '.join(lines[:1])
        l2 = ' '.join(lines[1:2])
        l3 = ' '.join(lines[2:])
        return f"{l1}\\N{l2}\\N{l3}"
    return "\\N".join(lines)

def split_sentence_into_subcues(text, start_ms, end_ms, max_chunk_len=24):
    """
    If a sentence is long, splits it into smaller balanced sub-cues mapped cleanly over [start_ms, end_ms].
    """
    text = text.strip()
    if not text or len(text) <= max_chunk_len:
        return [(text, start_ms, end_ms)]
    
    raw_clauses = [c for c in re.split(r'([，。！？；:\n,!?])', text) if c]
    clauses = []
    curr = ""
    for c in raw_clauses:
        curr += c
        if c in '，。！？；:\n,!?':
            clauses.append(curr.strip())
            curr = ""
    if curr.strip():
        clauses.append(curr.strip())

    chunks = []
    curr_chunk = ""
    for cl in clauses:
        if not curr_chunk:
            curr_chunk = cl
        elif len(curr_chunk) + len(cl) <= max_chunk_len:
            curr_chunk += (" " if (curr_chunk[-1].isascii() and cl[0].isascii()) else "") + cl
        else:
            chunks.append(curr_chunk)
            curr_chunk = cl
    if curr_chunk:
        chunks.append(curr_chunk)

    weights = [calc_text_weight(c) for c in chunks]
    total_w = sum(weights)
    if total_w == 0:
        return [(text, start_ms, end_ms)]

    duration = end_ms - start_ms
    res = []
    c_start = start_ms
    for idx, (c, w) in enumerate(zip(chunks, weights)):
        c_dur = duration * (w / total_w) if idx < len(chunks) - 1 else (end_ms - c_start)
        c_end = c_start + c_dur
        res.append((c, c_start, c_end))
        c_start = c_end
    return res

async def generate_audio_ass_and_slide_durations(script_text, voice, target_num_slides, out_audio, out_ass, rate="+25%"):
    print(f"🎙️ Generating TTS audio with voice [{voice}] (Speed {rate})...")
    clean_script, sentences_info, effective_num_slides = parse_script_and_slides(script_text, target_num_slides)
    
    communicate = edge_tts.Communicate(clean_script, voice, rate=rate, pitch="+0Hz")
    boundaries = []
    
    with open(out_audio, "wb") as audio_f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_f.write(chunk["data"])
            elif chunk["type"] == "SentenceBoundary":
                boundaries.append(chunk)

    print("📝 Generating high-precision ASS subtitles and slide content timings...")
    total_audio_ms = get_audio_duration_ms(out_audio)
    if total_audio_ms <= 0:
        total_audio_ms = 10000.0

    slide_timing = {i: {"start": None, "end": None} for i in range(1, effective_num_slides + 1)}
    dialogues = []

    # Map boundaries to sentences & slide indices
    if boundaries:
        for idx, b in enumerate(boundaries):
            s_info = sentences_info[idx] if idx < len(sentences_info) else sentences_info[-1]
            s_idx = s_info["slide_idx"]
            s_ms = b["offset"] / 10000.0
            e_ms = (b["offset"] + b["duration"]) / 10000.0

            if slide_timing[s_idx]["start"] is None:
                slide_timing[s_idx]["start"] = s_ms
            slide_timing[s_idx]["end"] = e_ms

            sub_cues = split_sentence_into_subcues(b["text"], s_ms, e_ms)
            for chunk_txt, chunk_s_ms, chunk_e_ms in sub_cues:
                formatted = smart_format_subtitle(chunk_txt, max_line_len=15)
                if not formatted:
                    continue
                s_ass = ms_to_ass(chunk_s_ms)
                e_ass = ms_to_ass(chunk_e_ms)
                dialogues.append(f"Dialogue: 0,{s_ass},{e_ass},Default,,0,0,0,,{formatted}")
    else:
        # Fallback if no boundary events returned
        weights = [calc_text_weight(s["text"]) for s in sentences_info]
        total_weight = sum(weights) or 1.0
        curr_start = 0.0
        for idx, (s_info, w) in enumerate(zip(sentences_info, weights)):
            dur = total_audio_ms * (w / total_weight) if idx < len(sentences_info) - 1 else (total_audio_ms - curr_start)
            curr_end = curr_start + dur
            s_idx = s_info["slide_idx"]
            if slide_timing[s_idx]["start"] is None:
                slide_timing[s_idx]["start"] = curr_start
            slide_timing[s_idx]["end"] = curr_end

            sub_cues = split_sentence_into_subcues(s_info["text"], curr_start, curr_end)
            for chunk_txt, s_ms, e_ms in sub_cues:
                formatted = smart_format_subtitle(chunk_txt, max_line_len=15)
                if not formatted:
                    continue
                s_ass = ms_to_ass(s_ms)
                e_ass = ms_to_ass(e_ms)
                dialogues.append(f"Dialogue: 0,{s_ass},{e_ass},Default,,0,0,0,,{formatted}")
            curr_start = curr_end

    # Normalize slide timings for continuous display without looping
    if slide_timing[1]["start"] is not None:
        slide_timing[1]["start"] = 0.0
    else:
        slide_timing[1]["start"] = 0.0

    for i in range(1, effective_num_slides):
        if slide_timing[i + 1]["start"] is not None:
            slide_timing[i]["end"] = slide_timing[i + 1]["start"]
        elif slide_timing[i]["end"] is None:
            slide_timing[i]["end"] = slide_timing[i]["start"] + 5000.0

    slide_timing[effective_num_slides]["end"] = max(
        slide_timing[effective_num_slides]["end"] or total_audio_ms,
        total_audio_ms
    )

    # ASS Header for 1080x1920 with bottom reserved subtitle zone
    ass_header = """[Script Info]
Title: Auto Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.601
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,PingFang SC,42,&H00FFFFFF,&H000000FF,&H00000000,&HA0080B15,1,0,0,0,100,100,0,0,3,10,0,2,60,60,100,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    with open(out_ass, "w", encoding="utf-8") as f:
        f.write(ass_header + "\n".join(dialogues))
        
    print(f"✓ Audio saved: {out_audio} ({total_audio_ms/1000:.1f}s)")
    print(f"✓ ASS Subtitles saved: {out_ass} ({len(dialogues)} cues, exact boundary aligned)")

    return slide_timing, effective_num_slides

def parse_script_and_slides(script_text, target_num_slides):
    """
    Parses script text into slide-associated sentences and produces clean text for TTS.
    Supports explicit tags like [SLIDE: 1] or fallback sentence/paragraph partitioning.
    """
    lines = script_text.splitlines()
    sentences_info = []
    current_slide = 1
    has_explicit_tags = bool(re.search(r'\[SLIDE:\s*\d+\]', script_text, re.IGNORECASE))
    
    if has_explicit_tags:
        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue
            m = re.match(r'\[SLIDE:\s*(\d+)\]', line_str, re.IGNORECASE)
            if m:
                current_slide = int(m.group(1))
            else:
                clauses = [s.strip() for s in re.split(r'([。！？\n])', line_str) if s.strip()]
                curr = ""
                for s in clauses:
                    curr += s
                    if s in '。！？\n':
                        sentences_info.append({"slide_idx": current_slide, "text": curr})
                        curr = ""
                if curr:
                    sentences_info.append({"slide_idx": current_slide, "text": curr})
    else:
        paragraphs = [p.strip() for p in script_text.split("\n\n") if p.strip()]
        if len(paragraphs) == target_num_slides:
            for idx, p in enumerate(paragraphs, start=1):
                clauses = [s.strip() for s in re.split(r'([。！？\n])', p) if s.strip()]
                curr = ""
                for s in clauses:
                    curr += s
                    if s in '。！？\n':
                        sentences_info.append({"slide_idx": idx, "text": curr})
                        curr = ""
                if curr:
                    sentences_info.append({"slide_idx": idx, "text": curr})
        else:
            all_sents = []
            for line in lines:
                line_str = line.strip()
                if not line_str:
                    continue
                clauses = [s.strip() for s in re.split(r'([。！？\n])', line_str) if s.strip()]
                curr = ""
                for s in clauses:
                    curr += s
                    if s in '。！？\n':
                        all_sents.append(curr)
                        curr = ""
                if curr:
                    all_sents.append(curr)
            
            total_len = sum(len(s) for s in all_sents) or 1
            cum_len = 0
            for s in all_sents:
                s_idx = min(target_num_slides, int(cum_len / total_len * target_num_slides) + 1)
                sentences_info.append({"slide_idx": s_idx, "text": s})
                cum_len += len(s)

    clean_script_text = "\n".join(item["text"] for item in sentences_info)
    max_slide_found = max([item["slide_idx"] for item in sentences_info], default=target_num_slides)
    effective_num_slides = max(target_num_slides, max_slide_found)
    
    return clean_script_text, sentences_info, effective_num_slides

def build_concat_file(slide_timing, effective_num_slides, out_dir):
    concat_path = os.path.join(out_dir, "concat.txt")
    lines = []
    print(f"🖼️ Slide Display Timings (Content-Synchronized, No Looping):")
    for i in range(1, effective_num_slides + 1):
        st = slide_timing.get(i, {"start": 0.0, "end": 5000.0})
        start_s = (st["start"] or 0.0) / 1000.0
        end_s = (st["end"] or start_s + 5.0) / 1000.0
        dur_s = max(0.5, end_s - start_s)
        img_file = os.path.join(out_dir, f"{i}.png")
        lines.append(f"file '{img_file}'")
        lines.append(f"duration {dur_s:.3f}")
        print(f"   - Slide {i}.png: {start_s:.2f}s -> {end_s:.2f}s ({dur_s:.2f}s)")
    
    lines.append(f"file '{os.path.join(out_dir, f'{effective_num_slides}.png')}'")

    with open(concat_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return concat_path

def render_video(concat_file, audio_path, ass_path, output_mp4):
    print("🎬 Rendering MP4 video (1.25x speed, 24fps smooth subtitle sampling)...")
    
    work_dir = os.path.dirname(os.path.abspath(ass_path))
    ass_rel = os.path.basename(ass_path)
    concat_rel = os.path.basename(concat_file)
    audio_rel = os.path.basename(audio_path)
    output_rel = os.path.basename(output_mp4)
    
    vf_filter = f"fps=24,scale=1080:1920,format=yuv420p,subtitles='{ass_rel}'"
    af_filter = "loudnorm"
    
    cmd = [
        "ffmpeg", "-y",
        "-hwaccel", "videotoolbox",
        "-f", "concat", "-safe", "0", "-i", concat_rel,
        "-i", audio_rel,
        "-vf", vf_filter,
        "-c:v", "h264_videotoolbox", "-b:v", "2M", "-r", "24", "-tag:v", "avc1",
        "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "128k",
        "-af", af_filter,
        "-shortest",
        "-movflags", "+faststart",
        output_rel
    ]
    
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=work_dir)
    if res.returncode == 0:
        print(f"✅ Video render complete: {os.path.join(work_dir, output_rel)}")
    else:
        print(f"⚠️ Videotoolbox failed, retrying with software libx264...")
        cmd_sw = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", concat_rel,
            "-i", audio_rel,
            "-vf", vf_filter,
            "-c:v", "libx264", "-preset", "medium", "-crf", "22", "-r", "24",
            "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "128k",
            "-af", af_filter,
            "-shortest",
            "-movflags", "+faststart",
            output_rel
        ]
        res_sw = subprocess.run(cmd_sw, capture_output=True, text=True, cwd=work_dir)
        if res_sw.returncode == 0:
            print(f"✅ Software render complete: {os.path.join(work_dir, output_rel)}")
        else:
            print(f"❌ Render failed: {res_sw.stderr}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Content to Podcast Video Skill Runner")
    parser.add_argument("--dir", default=None,
                        help="Working/output directory (default: the --script-file's directory, else cwd)")
    parser.add_argument("--slides", type=int, default=6, help="Number of slide images (1.png .. N.png)")
    parser.add_argument("--topic", default="tech", choices=["tech", "business", "story", "casual"])
    parser.add_argument("--script-file", help="Path to podcast script text file")
    parser.add_argument("--output", default="output.mp4", help="Output MP4 filename")
    parser.add_argument("--rate", default="+25%", help="TTS speech rate (default: +25% for 1.25x speed)")
    
    args = parser.parse_args()

    if shutil.which("ffmpeg") is None:
        print("❌ ffmpeg not found on PATH. Install it (e.g. `brew install ffmpeg`).")
        sys.exit(1)

    if not (args.script_file and os.path.exists(args.script_file)):
        print("Please provide a valid script file via --script-file")
        sys.exit(1)

    if args.dir is None:
        args.dir = os.path.dirname(os.path.abspath(args.script_file)) or os.getcwd()

    out_audio = os.path.join(args.dir, "podcast.mp3")
    out_ass = os.path.join(args.dir, "podcast.ass")
    out_mp4 = os.path.join(args.dir, args.output)

    with open(args.script_file, "r", encoding="utf-8") as f:
        script_text = f.read()

    voice = auto_select_voice(args.topic, script_text)
    slide_timing, effective_slides = asyncio.run(
        generate_audio_ass_and_slide_durations(script_text, voice, args.slides, out_audio, out_ass, rate=args.rate)
    )
    
    concat_file = build_concat_file(slide_timing, effective_slides, args.dir)
    render_video(concat_file, out_audio, out_ass, out_mp4)

