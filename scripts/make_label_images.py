"""Render synthetic packaging transcripts, or an explicitly unreadable blurred photo.

Examples (from the repository root):
    python scripts/make_label_images.py path/packaging.v1.json
    python scripts/make_label_images.py path/blurred_label.v2.json --blur --blur-source path/label.png
Pass --font /path/to/unicode.ttf when the platform has no supported Unicode font.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

CANVAS = (1280, 720)
MARGIN = 56


@dataclass(frozen=True)
class Label:
    path: Path
    transcript: str


def read_label(path: Path) -> Label:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("kind") != "PACKAGING_IMAGE":
        raise ValueError(f"{path}: expected PACKAGING_IMAGE")
    if value.get("dataset_origin") != "SYNTHETIC":
        raise ValueError(f"{path}: only synthetic labels may be rendered")
    passages = value.get("passages")
    if not isinstance(passages, list) or not passages:
        raise ValueError(f"{path}: passages must be a nonempty list")
    texts: list[str] = []
    for passage in passages:
        if not isinstance(passage, dict) or not isinstance(passage.get("text"), str):
            raise ValueError(f"{path}: each passage requires text")
        texts.append(passage["text"])
    return Label(path, "\n".join(texts).strip())


def load_font(size: int, path: Path | None = None) -> ImageFont.FreeTypeFont:
    candidates = [str(path)] if path else [
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "DejaVuSans.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    raise ValueError("No Unicode TrueType font available; supply --font")


def wrap_text(text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    """Wrap by measured pixels; split long tokens so no content is clipped."""
    lines: list[str] = []
    for paragraph in text.splitlines():
        line = ""
        for word in paragraph.split():
            candidate = f"{line} {word}" if line else word
            if font.getlength(candidate) <= width:
                line = candidate
                continue
            if line:
                lines.append(line)
                line = ""
            for char in word:
                if line and font.getlength(line + char) > width:
                    lines.append(line)
                    line = ""
                line += char
        lines.append(line)
    return lines


def render_transcript(text: str, font_path: Path | None = None) -> Image.Image:
    if not text.strip():
        raise ValueError("Readable label requires a nonempty transcript")
    width = CANVAS[0] - 2 * MARGIN
    for size in range(32, 23, -2):
        font = load_font(size, font_path)
        lines = wrap_text(text, font, width)
        ascent, descent = font.getmetrics()
        step = ascent + descent + 12
        if len(lines) * step <= CANVAS[1] - 2 * MARGIN:
            break
    else:
        raise ValueError("Transcript does not fit 1280x720 at readable font size; split the source image")
    image = Image.new("RGB", CANVAS, "#f8f5ed")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((24, 24, 1255, 695), radius=16, outline="#71867d", width=3)
    for index, line in enumerate(lines):
        draw.text((MARGIN, MARGIN + index * step), line, font=font, fill="#173e35", anchor="lt")
    return image


def render_label(
    path: Path, *, blur: bool = False, blur_source: Path | None = None,
    font_path: Path | None = None,
) -> Path:
    label = read_label(path)
    if blur:
        if label.transcript:
            raise ValueError("Blurred label must have an empty transcript")
        if blur_source is None:
            raise ValueError("--blur requires --blur-source pointing to a rendered label")
        if blur_source.resolve() == path.with_suffix(".png").resolve():
            raise ValueError("Blur source and destination must differ")
        with Image.open(blur_source) as original:
            # Heavy downsampling destroys character strokes before Gaussian blur.
            image = original.convert("RGB").resize((32, 18), Image.Resampling.BOX)
            image = image.resize(CANVAS, Image.Resampling.BILINEAR).filter(ImageFilter.GaussianBlur(24))
    else:
        if blur_source is not None:
            raise ValueError("--blur-source requires --blur")
        image = render_transcript(label.transcript, font_path)
    destination = path.with_suffix(".png")
    image.save(destination, format="PNG")
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshots", nargs="+", type=Path)
    parser.add_argument("--font", type=Path)
    parser.add_argument("--blur", action="store_true")
    parser.add_argument("--blur-source", type=Path)
    args = parser.parse_args(argv)
    try:
        for path in args.snapshots:
            output = render_label(path, blur=args.blur, blur_source=args.blur_source, font_path=args.font)
            print(output)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Label rendering failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
