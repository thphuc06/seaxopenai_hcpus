"""P2 OCR interface; implementation due at S4."""
from dataclasses import dataclass


@dataclass
class Box:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    conf: float
    w: int
    h: int


def index_image(sv_id: str) -> None:
    return None


def boxes_for(sv_id: str, excerpt: str) -> list[Box]:
    return []
