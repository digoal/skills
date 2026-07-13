#!/usr/bin/env python3
"""Render poster HTML pages to exact-size PNGs via Chrome headless.

Each `page-N.html` in the input dir is rendered to `N.png` in the output dir.
Page 1 is the cover; pages 2..N are content pages. Output is forced to the
exact target size (default 1080x1920) — if Chrome produces a different size the
image is padded/cropped so downstream consumers get consistent dimensions.

Usage:
  render.py --in <html-dir> --out <png-dir> [--width 1080] [--height 1920]
  render.py page-1.html page-2.html --out <png-dir>   # explicit file list
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile

from PIL import Image

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
]


def find_chrome():
    for p in CHROME_CANDIDATES:
        if os.path.exists(p):
            return p
    for name in ("google-chrome", "chromium", "chromium-browser", "chrome"):
        from shutil import which
        p = which(name)
        if p:
            return p
    sys.exit("ERROR: Chrome/Chromium not found. Install Google Chrome or set a path in CHROME_CANDIDATES.")


def natural_key(s):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


def discover(indir):
    files = [f for f in os.listdir(indir) if re.match(r"page-\d+\.html$", f)]
    files.sort(key=natural_key)
    return [os.path.join(indir, f) for f in files]


def render_one(chrome, html_path, png_path, w, h):
    subprocess.run(
        [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--hide-scrollbars",
            "--force-device-scale-factor=1",
            f"--window-size={w},{h}",
            f"--screenshot={png_path}",
            f"file://{os.path.abspath(html_path)}",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Enforce exact dimensions.
    im = Image.open(png_path).convert("RGB")
    if im.size != (w, h):
        canvas = Image.new("RGB", (w, h), (255, 255, 255))
        canvas.paste(im, (0, 0))
        canvas.save(png_path)
        return f"{im.size} -> forced {w}x{h}"
    im.save(png_path)
    return f"{w}x{h} ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*", help="explicit HTML files (page-N.html); overrides --in")
    ap.add_argument("--in", dest="indir", help="directory containing page-N.html files")
    ap.add_argument("--out", dest="outdir", required=True, help="output directory for N.png")
    ap.add_argument("--width", type=int, default=1080)
    ap.add_argument("--height", type=int, default=1920)
    args = ap.parse_args()

    chrome = find_chrome()
    if args.files:
        files = sorted(args.files, key=natural_key)
    elif args.indir:
        files = discover(args.indir)
    else:
        sys.exit("ERROR: provide either a file list or --in <dir>")

    if not files:
        sys.exit("ERROR: no page-N.html files found")

    os.makedirs(args.outdir, exist_ok=True)
    for i, html in enumerate(files, start=1):
        out = os.path.join(args.outdir, f"{i}.png")
        with tempfile.NamedTemporaryFile(suffix=".png", delete=True) as tmp:
            status = render_one(chrome, html, tmp.name, args.width, args.height)
            Image.open(tmp.name).save(out)
        label = "cover" if i == 1 else f"content {i-1}"
        print(f"[{label}] {os.path.basename(html)} -> {out}  ({status})")

    print(f"\nDone: {len(files)} PNG(s) in {args.outdir}")


if __name__ == "__main__":
    main()
