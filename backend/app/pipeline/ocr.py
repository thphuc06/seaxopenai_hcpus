"""Local OCR with versioned transcripts; cached boxes never mutate stored passages."""
from contextlib import closing
from functools import lru_cache
from threading import Lock
import sqlite3
import unicodedata
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, model_validator
from app import config, db, source_images

if TYPE_CHECKING:
    from rapidocr_onnxruntime import RapidOCR

OCR_VERSION = "rapidocr-onnxruntime-1.4.4:transcript-v1:confidence-0.8"
_lock = Lock()


class Box(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    x0: float = Field(ge=0)
    y0: float = Field(ge=0)
    x1: float = Field(ge=0)
    y1: float = Field(ge=0)
    text: str = Field(min_length=1)
    conf: float = Field(ge=0, le=1)
    w: int = Field(gt=0)
    h: int = Field(gt=0)

    @model_validator(mode="after")
    def bounds(self) -> "Box":
        if not (self.x0 < self.x1 <= self.w and self.y0 < self.y1 <= self.h) or not self.text.strip():
            raise ValueError("Invalid OCR box")
        return self


@lru_cache(maxsize=1)
def _engine() -> "RapidOCR":
    from rapidocr_onnxruntime import RapidOCR
    return RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1)


def _recognize(data: bytes) -> list[Box]:
    """Replaceable local-engine seam. Models are bundled with the pinned package."""
    from cv2 import error as CVError
    from rapidocr_onnxruntime.utils.infer_engine import ONNXRuntimeError
    from rapidocr_onnxruntime.utils.load_image import LoadImageError
    from rapidocr_onnxruntime.utils.process_img import ResizeImgError
    from rapidocr_onnxruntime.ch_ppocr_det.utils import ResizeImgError as DetectionResizeError

    _, width, height = source_images.validate_image(data)
    try:
        with _lock:
            result, _ = _engine()(data)
    except (ONNXRuntimeError, LoadImageError, ResizeImgError, DetectionResizeError, CVError) as error:
        raise RuntimeError("Local OCR processing failed") from error
    boxes: list[Box] = []
    for polygon, text, confidence in result or []:
        if confidence < 0.8 or not text.strip():
            continue
        xs, ys = [float(point[0]) for point in polygon], [float(point[1]) for point in polygon]
        boxes.append(Box(x0=min(xs), y0=min(ys), x1=max(xs), y1=max(ys), text=text, conf=confidence, w=width, h=height))
    return boxes


def transcribe(data: bytes) -> list[Box]:
    source_images.validate_image(data)
    return _recognize(data) if config.settings.ocr_enabled else []


def persist_lines(connection: sqlite3.Connection, sv_id: str, lines: list[Box]) -> None:
    for index, box in enumerate(lines):
        connection.execute("INSERT OR IGNORE INTO ocr_lines(source_version_id,idx,text,x0,y0,x1,y1,conf,w,h) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (sv_id, index, box.text, box.x0, box.y0, box.x1, box.y1, box.conf, box.w, box.h))


def index_image(sv_id: str) -> None:
    if not config.settings.ocr_enabled:
        return
    with closing(db.connect()) as connection:
        if connection.execute("SELECT 1 FROM ocr_lines WHERE source_version_id=? LIMIT 1", (sv_id,)).fetchone():
            return
        source = connection.execute("SELECT v.raw_path FROM source_versions v JOIN sources s ON s.id=v.source_id WHERE v.id=? AND s.kind='PACKAGING_IMAGE'", (sv_id,)).fetchone()
    if not source or not source["raw_path"]:
        return
    data, _, _, _ = source_images.read_image(source["raw_path"])
    lines = transcribe(data)
    with db.transaction() as connection:
        persist_lines(connection, sv_id, lines)


def boxes_for(sv_id: str, excerpt: str) -> list[Box]:
    """Read only: return boxes for a contiguous normalized quote, never fuzzy matches."""
    clean = lambda text: " ".join(unicodedata.normalize("NFC", text).split())
    quote = clean(excerpt)
    if not quote or not config.settings.db_path.exists():
        return []
    uri = config.settings.db_path.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        # Before startup there is no OCR cache; a read must not initialize it.
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ocr_lines'").fetchone():
            return []
        lines = [Box.model_validate(dict(row)) for row in connection.execute(
            "SELECT text,x0,y0,x1,y1,conf,w,h FROM ocr_lines WHERE source_version_id=? ORDER BY idx", (sv_id,))]
    text = " ".join(clean(line.text) for line in lines)
    start = text.find(quote)
    if start < 0:
        return []
    offset, selected = 0, []
    for line in lines:
        end = offset + len(clean(line.text))
        if offset < start + len(quote) and end > start:
            selected.append(line)
        offset = end + 1
    return selected
