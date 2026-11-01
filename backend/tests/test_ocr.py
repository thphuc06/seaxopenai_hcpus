import base64
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image
from fastapi.testclient import TestClient

from app import config, db, store
from app.main import create_app
from app.pipeline import ocr
from p1_helpers import CoreDB, core_db


def image_bytes() -> bytes:
    stream = BytesIO()
    Image.new("RGB", (100, 60), "white").save(stream, format="PNG")
    return stream.getvalue()


def lines() -> list[ocr.Box]:
    return [ocr.Box(x0=2, y0=2 + n * 20, x1=95, y1=19 + n * 20, text=text, conf=0.95, w=100, h=60)
            for n, text in enumerate(["Volume: 83 ml.", "For dry skin."])]


def test_upload_image_versions_transcript_once_and_extracts_real_passage(core_db: CoreDB, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "fixtures_dir", tmp_path)
    monkeypatch.setattr(config.settings, "ocr_enabled", True)
    calls = []
    def engine(data: bytes) -> list[ocr.Box]:
        calls.append(data)
        return lines()
    monkeypatch.setattr(ocr, "_recognize", engine)
    request = {"idempotency_key": "unseen-image", "field_keys": ["volume", "skin_type"],
               "content": {"kind": "IMAGE", "media_type": "image/png", "data_base64": base64.b64encode(image_bytes()).decode()}}
    with TestClient(create_app()) as client:
        url = f"/api/cases/{core_db.case_id}/evidence"
        headers = {"X-Demo-Role": "SELLER", "X-Demo-Actor": "uploader"}
        response = client.post(url, json=request, headers=headers)
        assert response.status_code == 200 and response.json()["outcome"] == "ADMITTED"
        source = core_db.rows("SELECT * FROM source_versions")[0]
        passages = store.passages(source["id"])
        assert passages[0]["text"] == "Volume: 83 ml.\nFor dry skin."
        assert len(core_db.rows("SELECT * FROM ocr_lines")) == 2
        claims = core_db.rows("SELECT * FROM claims WHERE field_key='volume'")
        assert claims and claims[0]["passage_id"] == passages[0]["id"]
        assert claims[0]["quote"] in passages[0]["text"]
        assert client.post(url, json=request, headers=headers).json()["outcome"] == "DUPLICATE"
        assert len(calls) == 1
        assert client.get(f"/api/sources/{source['id']}/image?as_role=BUYER").status_code == 403
        assert client.get(f"/api/sources/{source['id']}/image?as_role=REVIEWER").content == image_bytes()
    before = core_db.dump()
    assert [b.text for b in ocr.boxes_for(source["id"], "83 ml. For dry")] == [b.text for b in lines()]
    assert ocr.boxes_for(source["id"], "84 ml.") == []
    assert ocr.boxes_for(source["id"], "") == []
    ocr.index_image(source["id"])
    assert len(calls) == 1 and core_db.dump() == before


def test_upload_rejects_magic_only_image_without_event(core_db: CoreDB, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "fixtures_dir", tmp_path)
    before = core_db.dump()
    with TestClient(create_app()) as client:
        response = client.post(f"/api/cases/{core_db.case_id}/evidence", headers={"X-Demo-Role": "SELLER", "X-Demo-Actor": "uploader"},
            json={"idempotency_key": "bad-image", "field_keys": ["volume"], "content": {"kind": "IMAGE", "media_type": "image/png",
                  "data_base64": base64.b64encode(b"\x89PNG\r\n\x1a\nnot an image").decode()}})
        assert response.status_code == 422
    assert core_db.dump() == before


def test_index_existing_image_never_rewrites_hashed_passages(core_db: CoreDB, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "fixtures_dir", tmp_path)
    monkeypatch.setattr(config.settings, "ocr_enabled", True)
    monkeypatch.setattr(ocr, "_recognize", lambda data: lines())
    image = tmp_path / "label.png"
    image.write_bytes(image_bytes())
    source = core_db.source(text="Prior captured label transcription.")
    with db.transaction() as connection:
        connection.execute("UPDATE source_versions SET raw_path=? WHERE id=?", (str(image), source.source_version_id))
    before = store.passages(source.source_version_id)
    ocr.index_image(source.source_version_id)
    assert store.passages(source.source_version_id) == before
    assert len(core_db.rows("SELECT * FROM ocr_lines")) == 2


@pytest.mark.parametrize("error_kind", ["onnx", "load", "resize", "detect_resize"])
def test_engine_failures_are_sanitized_at_upload_boundary(core_db: CoreDB, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error_kind: str) -> None:
    from rapidocr_onnxruntime.utils.infer_engine import ONNXRuntimeError
    from rapidocr_onnxruntime.utils.load_image import LoadImageError
    from rapidocr_onnxruntime.utils.process_img import ResizeImgError
    from rapidocr_onnxruntime.ch_ppocr_det.utils import ResizeImgError as DetectionResizeError
    errors = {"onnx": ONNXRuntimeError, "load": LoadImageError, "resize": ResizeImgError, "detect_resize": DetectionResizeError}
    def engine(data: bytes):
        raise errors[error_kind]("PRIVATE ENGINE DETAILS")
    monkeypatch.setattr(ocr, "_engine", lambda: engine)
    monkeypatch.setattr(config.settings, "fixtures_dir", tmp_path)
    monkeypatch.setattr(config.settings, "ocr_enabled", True)
    before = core_db.dump()
    with TestClient(create_app()) as client:
        response = client.post(f"/api/cases/{core_db.case_id}/evidence", headers={"X-Demo-Role": "SELLER", "X-Demo-Actor": "uploader"},
            json={"idempotency_key": "engine-error", "field_keys": ["volume"], "content": {"kind": "IMAGE", "media_type": "image/png", "data_base64": base64.b64encode(image_bytes()).decode()}})
    assert response.status_code == 503 and "PRIVATE" not in response.text
    assert core_db.dump() == before


def test_local_engine_adapter_preserves_geometry_and_filters_low_confidence(monkeypatch: pytest.MonkeyPatch) -> None:
    polygon = [[2, 4], [70, 4], [70, 25], [2, 25]]
    monkeypatch.setattr(ocr, "_engine", lambda: lambda data: ([[polygon, "Unreadable", 0.4], [polygon, "83 ml", 0.97]], []))
    boxes = ocr._recognize(image_bytes())
    assert len(boxes) == 1 and boxes[0].text == "83 ml"
    assert (boxes[0].x0, boxes[0].y0, boxes[0].x1, boxes[0].y1, boxes[0].w, boxes[0].h) == (2, 4, 70, 25, 100, 60)
