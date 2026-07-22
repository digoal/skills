#!/usr/bin/env python3
"""
Content to Podcast Video Generator
Automates: Slide HTML/PNG generation -> TTS Audio -> 1.25x ASS Subtitles -> MP4 Video
"""

import os
import sys
import re
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
    s, ms = divmod(int(ms), 1000)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    cs = ms // 10
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def clean_split(text, max_len=18):
    text = text.strip()
    if len(text) <= max_len:
        return text
        
    best_idx = -1
    for i in range(min(max_len, len(text) - 1), 3, -1):
        if text[i] in '，；、。！？— ':
            best_idx = i + (1 if text[i] not in '—' else 0)
            break
            
    if best_idx == -1:
        words = re.findall(r'[a-zA-Z0-9]+|[\u4e00-\u9fa5]|.', text)
        line1, line2 = "", ""
        for w in words:
            if len(line1) + len(w) <= max_len:
                line1 += w
            else:
                line2 += w
        return f"{line1.strip()}\\N{line2.strip()}"
    else:
        l1 = text[:best_idx].strip()
        l2 = text[best_idx:].strip()
        return f"{l1}\\N{l2}" if l2 else l1

async def generate_audio_and_ass(script_text, voice, out_audio, out_ass, speed_factor=1.25):
    print(f"🎙️ Generating TTS audio with voice [{voice}] (Normal speed 1.0x)...")
    communicate = edge_tts.Communicate(script_text, voice, rate="+0%", pitch="+0Hz")
    sub_maker = edge_tts.SubMaker()

    with open(out_audio, "wb") as audio_f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_f.write(chunk["data"])
            elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
                sub_maker.feed(chunk)

    print("📝 Building 1.25x speed-adjusted ASS subtitles...")
    dialogues = []
    
    # Process sub_maker cues
    for cue in sub_maker.cues:
        start_ms = cue.start / 10000 / speed_factor  # 100ns units to ms, scaled by 1.25
        end_ms = cue.end / 10000 / speed_factor
        text = cue.text.strip()
        text = text.replace("——", "—— ")
        
        # Split long clauses
        clauses = [c.strip() for c in re.split(r'([，；。！？])', text) if c.strip()]
        chunks = []
        curr = ""
        for item in clauses:
            if item in '，；。！？':
                curr += item
                if len(curr) >= 10:
                    chunks.append(curr)
                    curr = ""
            else:
                if len(curr) + len(item) > 20:
                    if curr: chunks.append(curr)
                    curr = item
                else:
                    curr += item
        if curr: chunks.append(curr)
        if not chunks: chunks = [text]
        
        total_len = sum(len(c) for c in chunks)
        duration = end_ms - start_ms
        curr_start = start_ms
        
        for idx, chunk in enumerate(chunks):
            chunk_len = len(chunk)
            curr_end = end_ms if idx == len(chunks)-1 else curr_start + (duration * (chunk_len / total_len))
            formatted = clean_split(chunk, max_len=18)
            s_ass = ms_to_ass(curr_start)
            e_ass = ms_to_ass(curr_end)
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
Style: Default,PingFang SC,32,&H00FFFFFF,&H000000FF,&H00000000,&HA0080B15,1,0,0,0,100,100,0,0,3,10,0,2,90,90,110,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    with open(out_ass, "w", encoding="utf-8") as f:
        f.write(ass_header + "\n".join(dialogues))
        
    print(f"✓ Audio saved: {out_audio}")
    print(f"✓ ASS Subtitles saved: {out_ass} ({len(dialogues)} cues)")

def build_concat_file(num_slides, out_dir):
    concat_path = os.path.join(out_dir, "concat.txt")
    lines = []
    # Loop slides (3 seconds each) for ~30 cycles (~90 slides = ~270 seconds)
    for _ in range(40):
        for i in range(1, num_slides + 1):
            lines.append(f"file '{os.path.join(out_dir, f'{i}.png')}'")
            lines.append("duration 3")
    lines.append(f"file '{os.path.join(out_dir, f'{num_slides}.png')}'")
    
    with open(concat_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return concat_path

def render_video(concat_file, audio_path, ass_path, output_mp4, speed_factor=1.25):
    print("🎬 Rendering MP4 video (Videotoolbox Hardware Accelerated)...")
    
    vf_filter = f"scale=1080:1920,format=yuv420p,subtitles='{ass_path}'"
    af_filter = f"atempo={speed_factor},loudnorm"
    
    cmd = [
        "ffmpeg", "-y",
        "-hwaccel", "videotoolbox",
        "-f", "concat", "-safe", "0", "-i", concat_file,
        "-i", audio_path,
        "-vf", vf_filter,
        "-c:v", "h264_videotoolbox", "-b:v", "2M", "-r", "24", "-tag:v", "avc1",
        "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "128k",
        "-af", af_filter,
        "-shortest",
        "-movflags", "+faststart",
        output_mp4
    ]
    
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0:
        print(f"✅ Video render complete: {output_mp4}")
    else:
        print(f"⚠️ Videotoolbox failed, retrying with software libx264...")
        cmd_sw = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", concat_file,
            "-i", audio_path,
            "-vf", vf_filter,
            "-c:v", "libx264", "-preset", "medium", "-crf", "22", "-r", "24",
            "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "128k",
            "-af", af_filter,
            "-shortest",
            "-movflags", "+faststart",
            output_mp4
        ]
        res_sw = subprocess.run(cmd_sw, capture_output=True, text=True)
        if res_sw.returncode == 0:
            print(f"✅ Software render complete: {output_mp4}")
        else:
            print(f"❌ Render failed: {res_sw.stderr}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Content to Podcast Video Skill Runner")
    parser.add_argument("--dir", default=os.getcwd(), help="Target working directory")
    parser.add_argument("--slides", type=int, default=6, help="Number of slide images (1.png .. N.png)")
    parser.add_argument("--topic", default="tech", choices=["tech", "business", "story", "casual"])
    parser.add_argument("--script-file", help="Path to podcast script text file")
    parser.add_argument("--output", default="output.mp4", help="Output MP4 filename")
    
    args = parser.parse_args()
    
    out_audio = os.path.join(args.dir, "podcast.mp3")
    out_ass = os.path.join(args.dir, "podcast.ass")
    out_mp4 = os.path.join(args.dir, args.output)
    
    if args.script_file and os.path.exists(args.script_file):
        with open(args.script_file, "r", encoding="utf-8") as f:
            script_text = f.read()
    else:
        print("Please provide a script file via --script-file")
        sys.exit(1)
        
    voice = auto_select_voice(args.topic, script_text)
    asyncio.run(generate_audio_and_ass(script_text, voice, out_audio, out_ass, speed_factor=1.25))
    
    concat_file = build_concat_file(args.slides, args.dir)
    render_video(concat_file, out_audio, out_ass, out_mp4, speed_factor=1.25)
