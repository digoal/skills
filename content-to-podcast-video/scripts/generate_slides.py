#!/usr/bin/env python3
"""
Slide Generator Script for Content to Podcast Video Skill
Generates 1080x1920 mobile presentation PNG images (1.png, 2.png, ...) using Chrome Headless.
Enforces a reserved clean subtitle area (bottom 200px) on every slide.
"""

import os
import sys
import subprocess

COMMON_CSS = """
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    width: 1080px;
    height: 1920px;
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "PingFang SC", "Hiragino Sans GB", sans-serif;
    color: #F3F4F6;
    overflow: hidden;
    position: relative;
    background-color: #080B15;
  }
  .bg {
    position: absolute;
    top: 0; left: 0; right: 0; bottom: 0;
    z-index: 0;
  }
  .wrap {
    position: relative;
    z-index: 1;
    width: 100%;
    height: 100%;
    /* Reserve bottom 220px for subtitles - no text/footers allowed below */
    padding: 80px 70px 220px 70px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
  }
  .sec-tag {
    display: inline-block;
    padding: 10px 24px;
    border-radius: 40px;
    background: rgba(6, 182, 212, 0.12);
    border: 1.5px solid rgba(6, 182, 212, 0.35);
    color: #67E8F9;
    font-size: 26px;
    font-weight: 700;
    letter-spacing: 2px;
    margin-bottom: 25px;
  }
  .sec-title {
    font-size: 58px;
    font-weight: 800;
    color: #FFFFFF;
    line-height: 1.2;
    margin-bottom: 40px;
  }
  .card {
    background: rgba(17, 24, 39, 0.75);
    border: 1.5px solid rgba(255, 255, 255, 0.1);
    border-radius: 24px;
    padding: 38px;
    margin-bottom: 24px;
  }
  .card-title {
    font-size: 36px;
    font-weight: 700;
    color: #FFFFFF;
    margin-bottom: 12px;
  }
  .card-desc {
    font-size: 28px;
    color: rgba(255, 255, 255, 0.6);
    line-height: 1.5;
  }
</style>
"""

def render_html_to_png(html_content, out_png_path):
    temp_html = f"{out_png_path}.html"
    with open(temp_html, "w", encoding="utf-8") as f:
        f.write(html_content)
        
    cmd = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "--headless",
        f"--screenshot={out_png_path}",
        "--window-size=1080,1920",
        "--hide-scrollbars",
        f"file://{temp_html}"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if os.path.exists(temp_html):
        os.remove(temp_html)
    return res.returncode == 0

if __name__ == "__main__":
    print("Slide Generator Module Loaded. See SKILL.md for usage details.")
