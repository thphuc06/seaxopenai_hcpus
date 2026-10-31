"""Typed multimodal input shared by the pipeline and the capability smoke."""

from __future__ import annotations

import base64
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypedDict


ImageDetail = Literal["low", "high", "original", "auto"]


@dataclass(frozen=True)
class TextPart:
    text: str


@dataclass(frozen=True)
class ImagePart:
    png_bytes: bytes | Path
    detail: ImageDetail = "high"


class InputText(TypedDict):
    type: Literal["input_text"]
    text: str


class InputImage(TypedDict):
    type: Literal["input_image"]
    image_url: str
    detail: ImageDetail


class InputMessage(TypedDict):
    role: Literal["system", "user"]
    content: list[InputText | InputImage]


def build_input(
    instructions: str, parts: Sequence[TextPart | ImagePart]
) -> list[InputMessage]:
    """Preserve part order; callers wrap untrusted source text in SOURCE_DATA."""
    if not instructions.strip():
        raise ValueError("Instructions must not be empty")
    if not parts:
        raise ValueError("At least one input part is required")
    content: list[InputText | InputImage] = []
    for part in parts:
        if isinstance(part, TextPart):
            content.append({"type": "input_text", "text": part.text})
        elif isinstance(part, ImagePart):
            if part.detail not in {"low", "high", "original", "auto"}:
                raise ValueError("Unsupported image detail")
            png = part.png_bytes.read_bytes() if isinstance(part.png_bytes, Path) else part.png_bytes
            if not isinstance(png, bytes) or not png.startswith(b"\x89PNG\r\n\x1a\n"):
                raise ValueError("ImagePart requires PNG bytes or a PNG Path")
            encoded = base64.b64encode(png).decode("ascii")
            content.append({"type": "input_image", "image_url": f"data:image/png;base64,{encoded}", "detail": part.detail})
        else:
            raise TypeError("Input parts must be TextPart or ImagePart")
    return [
        {"role": "system", "content": [{"type": "input_text", "text": instructions}]},
        {"role": "user", "content": content},
    ]
