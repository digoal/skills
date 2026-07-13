#!/usr/bin/env python3
"""Extract text, table candidates, and embedded images from a paper PDF."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import urllib.parse
import urllib.request
from pathlib import Path


def is_url(value: str) -> bool:
    parsed = urllib.parse.urlparse(value)
    return parsed.scheme in {"http", "https"}


def safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    return value.strip("-") or "paper"


def download(url: str, target: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "paper-interpretation/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        target.write_bytes(response.read())


def normalize_pdf(source: str, out_dir: Path) -> tuple[Path, list[str]]:
    warnings: list[str] = []
    pdf_path = out_dir / "paper.pdf"
    if is_url(source):
        download(source, pdf_path)
    else:
        source_path = Path(source).expanduser().resolve()
        if not source_path.exists():
            raise FileNotFoundError(f"PDF not found: {source_path}")
        if source_path.resolve() != pdf_path.resolve():
            shutil.copyfile(source_path, pdf_path)

    if pdf_path.stat().st_size == 0:
        raise ValueError("PDF is empty")
    digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    warnings.append(f"sha256={digest}")
    return pdf_path, warnings


def extract_text(pdf_path: Path, out_dir: Path) -> tuple[int | None, list[str]]:
    warnings: list[str] = []
    text_out = out_dir / "paper_text.md"

    try:
        import fitz  # type: ignore
    except Exception as exc:
        warnings.append(f"PyMuPDF unavailable for text extraction: {exc}")
    else:
        doc = fitz.open(pdf_path)
        with text_out.open("w", encoding="utf-8") as fh:
            fh.write("# Extracted Paper Text\n\n")
            for index, page in enumerate(doc, start=1):
                text = page.get_text("text").strip()
                fh.write(f"\n\n## Page {index}\n\n")
                fh.write(text if text else "[No extractable text on this page]")
                fh.write("\n")
        page_count = doc.page_count
        doc.close()
        return page_count, warnings

    try:
        from pypdf import PdfReader  # type: ignore
    except Exception as exc:
        warnings.append(f"pypdf unavailable for text extraction: {exc}")
        return None, warnings

    reader = PdfReader(str(pdf_path))
    with text_out.open("w", encoding="utf-8") as fh:
        fh.write("# Extracted Paper Text\n\n")
        for index, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            fh.write(f"\n\n## Page {index}\n\n")
            fh.write(text if text else "[No extractable text on this page]")
            fh.write("\n")
    return len(reader.pages), warnings


def extract_tables(pdf_path: Path, out_dir: Path) -> list[str]:
    warnings: list[str] = []
    table_out = out_dir / "paper_tables.md"
    try:
        import pdfplumber  # type: ignore
    except Exception as exc:
        warnings.append(f"pdfplumber unavailable for table extraction: {exc}")
        return warnings

    with pdfplumber.open(str(pdf_path)) as pdf, table_out.open("w", encoding="utf-8") as fh:
        fh.write("# Extracted Table Candidates\n\n")
        found = 0
        for page_index, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables() or []
            for table_index, table in enumerate(tables, start=1):
                found += 1
                fh.write(f"\n\n## Page {page_index} Table {table_index}\n\n")
                for row in table:
                    cells = [("" if cell is None else str(cell).replace("\n", " ")) for cell in row]
                    fh.write("| " + " | ".join(cells) + " |\n")
        if found == 0:
            fh.write("No table candidates found.\n")
    return warnings


def extract_images(pdf_path: Path, out_dir: Path) -> list[str]:
    warnings: list[str] = []
    figures_dir = out_dir / "figures"
    figures_dir.mkdir(exist_ok=True)

    try:
        import fitz  # type: ignore
    except Exception as exc:
        warnings.append(f"PyMuPDF unavailable for image extraction: {exc}")
        return warnings

    doc = fitz.open(pdf_path)
    count = 0
    for page_index in range(doc.page_count):
        page = doc[page_index]
        for image_index, image in enumerate(page.get_images(full=True), start=1):
            xref = image[0]
            data = doc.extract_image(xref)
            ext = safe_name(data.get("ext", "png"))
            image_bytes = data.get("image")
            if not image_bytes:
                continue
            count += 1
            name = f"page-{page_index + 1:03d}-image-{image_index:02d}.{ext}"
            (figures_dir / name).write_bytes(image_bytes)
    doc.close()

    if count == 0:
        warnings.append("No embedded images extracted; figures may be vector drawings or page-rendered content.")
    return warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Local PDF path or PDF URL")
    parser.add_argument("--out", default=".paper-work", help="Output directory")
    args = parser.parse_args()

    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, object] = {"input": args.input, "out_dir": str(out_dir), "warnings": []}
    warnings: list[str] = []

    try:
        pdf_path, normalize_warnings = normalize_pdf(args.input, out_dir)
        warnings.extend(normalize_warnings)
        page_count, text_warnings = extract_text(pdf_path, out_dir)
        warnings.extend(text_warnings)
        warnings.extend(extract_tables(pdf_path, out_dir))
        warnings.extend(extract_images(pdf_path, out_dir))
        manifest.update({"pdf": str(pdf_path), "page_count": page_count, "status": "ok"})
    except Exception as exc:
        manifest.update({"status": "error", "error": str(exc)})
        warnings.append(str(exc))

    manifest["warnings"] = warnings
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0 if manifest.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
