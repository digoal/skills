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

async def generate_audio_and_ass(script_text, voice, out_audio, out_ass):
    print(f"🎙️ Generating TTS audio with voice [{voice}] (Normal 1.0x speed)...")
    communicate = edge_tts.Communicate(script_text, voice, rate="+0%", pitch="+0Hz")

    with open(out_audio, "wb") as audio_f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_f.write(chunk["data"])

    print("📝 Generating text-authoritative 100% complete ASS subtitles...")
    total_audio_ms = get_audio_duration_ms(out_audio)
    if total_audio_ms <= 0:
        total_audio_ms = 10000.0

    # Extract 100% complete sentences directly from script_text (Source of Truth)
    raw_lines = [l.strip() for l in script_text.split("\n") if l.strip()]
    sentences = []
    for line in raw_lines:
        clauses = [s.strip() for s in re.split(r'([。！？\n])', line) if s.strip()]
        curr = ""
        for s in clauses:
            curr += s
            if s in '。！？\n':
                sentences.append(curr)
                curr = ""
        if curr:
            sentences.append(curr)

    weights = [calc_text_weight(s) for s in sentences]
    total_weight = sum(weights) or 1.0

    dialogues = []
    curr_start = 0.0
    for idx, (sent, w) in enumerate(zip(sentences, weights)):
        dur = total_audio_ms * (w / total_weight) if idx < len(sentences) - 1 else (total_audio_ms - curr_start)
        curr_end = curr_start + dur
        
        # Sub-divide long sentences for clean vertical readability
        sub_cues = split_sentence_into_subcues(sent, curr_start, curr_end)
        for chunk_txt, s_ms, e_ms in sub_cues:
            formatted = smart_format_subtitle(chunk_txt, max_line_len=15)
            if not formatted:
                continue
            s_ass = ms_to_ass(s_ms)
            e_ass = ms_to_ass(e_ms)
            dialogues.append(f"Dialogue: 0,{s_ass},{e_ass},Default,,0,0,0,,{formatted}")

        curr_start = curr_end

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
    print(f"✓ ASS Subtitles saved: {out_ass} ({len(dialogues)} cues, 100% script text covered)")

def build_concat_file(num_slides, out_dir, seconds=6):
    concat_path = os.path.join(out_dir, "concat.txt")
    lines = []
    cycles = max(1, int(3600 / (num_slides * seconds)) + 1)
    for _ in range(cycles):
        for i in range(1, num_slides + 1):
            lines.append(f"file '{os.path.join(out_dir, f'{i}.png')}'")
            lines.append(f"duration {seconds}")
    lines.append(f"file '{os.path.join(out_dir, f'{num_slides}.png')}'")

    with open(concat_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return concat_path

def render_video(concat_file, audio_path, ass_path, output_mp4):
    print("🎬 Rendering MP4 video (Normal speed, 24fps smooth subtitle sampling)...")
    
    work_dir = os.path.dirname(os.path.abspath(ass_path))
    ass_rel = os.path.basename(ass_path)
    concat_rel = os.path.basename(concat_file)
    audio_rel = os.path.basename(audio_path)
    output_rel = os.path.basename(output_mp4)
    
    # Prepend fps=24 to the filtergraph so concat demuxer's sparse image frames (e.g. every 6s)
    # are resampled to a continuous 24fps stream BEFORE entering the subtitles filter.
    # Without fps=24 first, subtitles filter only samples ASS events on sparse 6s boundaries,
    # causing all intermediate subtitle dialogues to be silently skipped in the rendered video.
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
    parser.add_argument("--seconds", type=int, default=6, help="Seconds each slide stays on screen")
    
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
    asyncio.run(generate_audio_and_ass(script_text, voice, out_audio, out_ass))
    
    concat_file = build_concat_file(args.slides, args.dir, seconds=args.seconds)
    render_video(concat_file, out_audio, out_ass, out_mp4)
