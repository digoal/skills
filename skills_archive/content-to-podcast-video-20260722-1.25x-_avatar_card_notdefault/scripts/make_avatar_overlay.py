#!/usr/bin/env python3
"""
make_avatar_overlay.py
======================
Generates a semi-transparent host portrait card (PNG, RGBA) to be overlaid
in the bottom-right corner of the podcast video.

The card contains:
  - Circular avatar photo (user-provided image)
  - Host name (bold white)
  - Host title/intro (smaller, cyan)
  - Static soundwave bars decoration (3 bars, cyan gradient)

The output is a transparent PNG sized to fit inside the subtitle reserved zone.

Usage (standalone):
    python3 make_avatar_overlay.py \
        --avatar /path/to/photo.jpg \
        --name "张伟" \
        --title "数据库架构师" \
        --output /path/to/avatar_card.png

Requirements:
    pip install pillow
"""

import os
import sys
import argparse
import math
from io import BytesIO

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
except ImportError:
    print("❌ Pillow not found. Install it: pip install pillow")
    sys.exit(1)

# Card dimensions (for 1080-wide video)
CARD_W = 420
CARD_H = 220
AVATAR_SIZE = 140          # diameter of circular avatar
CORNER_R = 28              # card corner radius
AVATAR_X = 24              # avatar left offset inside card
AVATAR_Y = (CARD_H - AVATAR_SIZE) // 2  # avatar vertically centered

# Soundwave bars (right side of card)
WAVE_BARS = 5
WAVE_BAR_W = 10
WAVE_BAR_GAP = 6
WAVE_BAR_MAX_H = 60
WAVE_BAR_MIN_H = 18
WAVE_X_START = CARD_W - 60  # right edge

FONT_PATH_CANDIDATES = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]

def find_font(size=32):
    """Try system fonts; fall back to PIL default."""
    for p in FONT_PATH_CANDIDATES:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size=size)
            except Exception:
                continue
    return ImageFont.load_default()

def draw_rounded_rect(draw, xy, radius, fill, border_color=None, border_width=2):
    """Draws a rounded rectangle on an ImageDraw object."""
    x0, y0, x1, y1 = xy
    draw.rectangle([x0 + radius, y0, x1 - radius, y1], fill=fill)
    draw.rectangle([x0, y0 + radius, x1, y1 - radius], fill=fill)
    draw.ellipse([x0, y0, x0 + 2 * radius, y0 + 2 * radius], fill=fill)
    draw.ellipse([x1 - 2 * radius, y0, x1, y0 + 2 * radius], fill=fill)
    draw.ellipse([x0, y1 - 2 * radius, x0 + 2 * radius, y1], fill=fill)
    draw.ellipse([x1 - 2 * radius, y1 - 2 * radius, x1, y1], fill=fill)
    if border_color:
        draw.arc([x0, y0, x0 + 2 * radius, y0 + 2 * radius], 180, 270, fill=border_color, width=border_width)
        draw.arc([x1 - 2 * radius, y0, x1, y0 + 2 * radius], 270, 360, fill=border_color, width=border_width)
        draw.arc([x0, y1 - 2 * radius, x0 + 2 * radius, y1], 90, 180, fill=border_color, width=border_width)
        draw.arc([x1 - 2 * radius, y1 - 2 * radius, x1, y1], 0, 90, fill=border_color, width=border_width)
        draw.line([x0 + radius, y0, x1 - radius, y0], fill=border_color, width=border_width)
        draw.line([x0 + radius, y1, x1 - radius, y1], fill=border_color, width=border_width)
        draw.line([x0, y0 + radius, x0, y1 - radius], fill=border_color, width=border_width)
        draw.line([x1, y0 + radius, x1, y1 - radius], fill=border_color, width=border_width)

def make_circular_avatar(img_path, size):
    """Opens avatar image, crops to square, resizes, and masks to circle."""
    try:
        img = Image.open(img_path).convert("RGBA")
    except Exception as e:
        print(f"⚠️  Could not open avatar image ({e}). Using placeholder.")
        img = Image.new("RGBA", (size, size), (100, 180, 220, 255))

    # Crop to square (center crop)
    w, h = img.size
    if w != h:
        s = min(w, h)
        left = (w - s) // 2
        top = (h - s) // 2
        img = img.crop((left, top, left + s, top + s))

    img = img.resize((size, size), Image.LANCZOS)

    # Create circular mask
    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse([0, 0, size, size], fill=255)

    # Soften mask edges slightly
    mask = mask.filter(ImageFilter.GaussianBlur(radius=1))

    result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    result.paste(img, (0, 0), mask)
    return result

def draw_soundwave_bars(draw, x_start, y_center, bars, bar_w, bar_gap, max_h, min_h, color):
    """
    Draws static soundwave bars (varying heights, symmetric around center bar).
    Heights: short, medium, tall, medium, short  (for 5 bars)
    """
    # Height pattern (ratio 0..1) — looks like a waveform
    patterns = {
        3: [0.5, 1.0, 0.5],
        4: [0.4, 1.0, 0.8, 0.4],
        5: [0.35, 0.72, 1.0, 0.72, 0.35],
        6: [0.3, 0.6, 1.0, 1.0, 0.6, 0.3],
        7: [0.25, 0.55, 0.85, 1.0, 0.85, 0.55, 0.25],
    }
    heights_ratio = patterns.get(bars, [0.5] * bars)

    # Calculate total width and center it around x_start
    total_w = bars * bar_w + (bars - 1) * bar_gap
    x0 = x_start - total_w // 2

    for i, ratio in enumerate(heights_ratio):
        h = int(min_h + (max_h - min_h) * ratio)
        x = x0 + i * (bar_w + bar_gap)
        y_top = y_center - h // 2
        y_bot = y_center + h // 2
        # Draw rounded bar
        radius = bar_w // 2
        draw.rounded_rectangle([x, y_top, x + bar_w, y_bot], radius=radius, fill=color)

def generate_avatar_card(avatar_path, host_name, host_title, output_path):
    """
    Generates the avatar card PNG (RGBA, transparent background).
    Card layout:
      [circular avatar] | [name\ntitle] | [soundwave]
    """
    card = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(card)

    # 1. Semi-transparent dark background card
    bg_color = (8, 11, 21, 200)   # #080B15 with ~78% opacity
    border_color = (6, 182, 212, 160)  # cyan border, semi-opaque
    draw_rounded_rect(draw, (0, 0, CARD_W - 1, CARD_H - 1),
                      radius=CORNER_R, fill=bg_color, border_color=border_color, border_width=2)

    # 2. Circular avatar
    avatar_img = make_circular_avatar(avatar_path, AVATAR_SIZE)
    # Cyan ring around avatar
    ring_draw = ImageDraw.Draw(card)
    ring_x = AVATAR_X - 3
    ring_y = AVATAR_Y - 3
    ring_size = AVATAR_SIZE + 6
    ring_draw.ellipse([ring_x, ring_y, ring_x + ring_size, ring_y + ring_size],
                      outline=(6, 182, 212, 220), width=3)
    card.paste(avatar_img, (AVATAR_X, AVATAR_Y), avatar_img)

    # 3. Text area (right of avatar)
    text_x = AVATAR_X + AVATAR_SIZE + 20

    # Host name
    font_name = find_font(34)
    font_title_f = find_font(24)

    name_y = 34
    draw.text((text_x, name_y), host_name or "digoal德哥", fill=(255, 255, 255, 240), font=font_name)

    # Host title / intro
    title_y = 85
    title_text = host_title or "数据库 & AI 专家"
    # Wrap title if too long
    if len(title_text) > 12:
        mid = len(title_text) // 2
        break_at = mid
        for offset in range(0, mid):
            if title_text[mid + offset] in '，,、 ':
                break_at = mid + offset + 1
                break
            if title_text[mid - offset] in '，,、 ':
                break_at = mid - offset
                break
        title_text = title_text[:break_at] + "\n" + title_text[break_at:]

    draw.multiline_text((text_x, title_y), title_text,
                        fill=(103, 232, 249, 220), font=font_title_f, spacing=6)

    # 4. Soundwave bars (positioned at bottom-right corner to avoid covering text)
    wave_cx = CARD_W - 65
    wave_cy = CARD_H - 38
    draw_soundwave_bars(
        draw, wave_cx, wave_cy,
        bars=WAVE_BARS, bar_w=8, bar_gap=5,
        max_h=32, min_h=12,
        color=(6, 182, 212, 210)
    )

    # 5. Small "LIVE" dot / pulse indicator to the left of soundwave
    dot_r = 5
    dot_x = wave_cx - 42
    dot_y = wave_cy
    draw.ellipse([dot_x - dot_r, dot_y - dot_r, dot_x + dot_r, dot_y + dot_r],
                 fill=(6, 182, 212, 255))
    draw.ellipse([dot_x - dot_r - 3, dot_y - dot_r - 3, dot_x + dot_r + 3, dot_y + dot_r + 3],
                 outline=(6, 182, 212, 100), width=2)

    card.save(output_path, "PNG")
    print(f"✓ Avatar card saved: {output_path} ({CARD_W}×{CARD_H}px)")
    return output_path

def main():
    ap = argparse.ArgumentParser(description="Generate host portrait overlay card for podcast videos")
    ap.add_argument("--avatar", required=True, help="Path to host avatar/portrait image")
    ap.add_argument("--name", default="", help="Host name (displayed on card)")
    ap.add_argument("--title", default="", help="Host title/intro (displayed on card)")
    ap.add_argument("--output", required=True, help="Output PNG path (RGBA transparent)")
    args = ap.parse_args()

    if not os.path.exists(args.avatar):
        print(f"❌ Avatar image not found: {args.avatar}")
        sys.exit(1)

    generate_avatar_card(args.avatar, args.name, args.title, args.output)

if __name__ == "__main__":
    main()
