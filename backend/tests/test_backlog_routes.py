"""Offline regression coverage for the previously unimplemented read routes."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import config, db
from app.main import create_app
from app.trace import TraceWriter
from p1_helpers import CoreDB, core_db


def headers(role: str = "OPERATOR") -> dict[str, str]:
    return {"X-Demo-Role": role, "X-Demo-Actor": "unit-reader"}


@pytest.mark.parametrize("format,suffix,media", [("PNG", ".png", "image/png"), ("JPEG", ".jpg", "image/jpeg"), ("WEBP", ".webp", "image/webp")])
def test_source_image_bytes_acl_and_read_only(core_db: CoreDB, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, format: str, suffix: str, media: str) -> None:
    monkeypatch.setattr(config.settings, "fixtures_dir", tmp_path)
    image = tmp_path / ("package" + suffix)
    Image.new("RGB", (23, 17), "white").save(image, format=format)
    source = core_db.source(visibility="PRIVATE")
    with db.transaction() as connection:
        connection.execute("UPDATE source_versions SET raw_path=? WHERE id=?", (str(image), source.source_version_id))
    before = core_db.dump()
    with TestClient(create_app()) as client:
        url = f"/api/sources/{source.source_version_id}/image"
        for role in ("BUYER", "SELLER", "SYSTEM"):
            assert client.get(url, params={"as_role": role}).status_code == 403
        for role in ("REVIEWER", "OPERATOR"):
            response = client.get(url, params={"as_role": role})
            assert response.status_code == 200
            assert response.content == image.read_bytes()
            assert response.headers["content-type"] == media
            assert response.headers["cache-control"] == "no-store"
        assert client.get(url).status_code == 422
    assert core_db.dump() == before


def test_source_image_rejects_unknown_non_image_and_outside_root(core_db: CoreDB, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "fixtures"
    root.mkdir()
    monkeypatch.setattr(config.settings, "fixtures_dir", root)
    source = core_db.source()
    outside = tmp_path / "outside.png"
    Image.new("RGB", (2, 2)).save(outside)
    with TestClient(create_app()) as client:
        url = f"/api/sources/{source.source_version_id}/image?as_role=BUYER"
        assert client.get("/api/sources/missing/image?as_role=BUYER").status_code == 404
        for path in (outside, root / "missing.png", root / "broken.png"):
            if path.name == "broken.png":
                path.write_bytes(b"\x89PNG\r\n\x1a\nnot an image")
            with db.transaction() as connection:
                connection.execute("UPDATE source_versions SET raw_path=? WHERE id=?", (str(path), source.source_version_id))
            response = client.get(url)
            assert response.status_code == 404
            assert str(tmp_path) not in response.text
        valid = root / "valid.png"
        Image.new("RGB", (2, 2)).save(valid)
        with db.transaction() as connection:
            connection.execute("UPDATE source_versions SET raw_path=? WHERE id=?", (str(valid), source.source_version_id))
        assert client.get(url).status_code == 200
        with db.transaction() as connection:
            connection.execute("UPDATE sources SET kind='SELLER_UPLOAD' WHERE id=?", (source.source_id,))
        assert client.get(url).status_code == 404


def test_otel_is_stored_deterministic_private_and_read_only(core_db: CoreDB) -> None:
    run = core_db.run()
    writer = TraceWriter(str(run["id"]))
    writer.step("extract", actor="llm", input_refs=["PRIVATE QUOTE"], latency_ms=25,
                tokens_in=12, tokens_out=3, detail={"model": "unit-model", "replayed": True, "prompt": "PRIVATE PROMPT"})
    writer.step("publish:blocked", error="PRIVATE ERROR", detail={"text": "PRIVATE DOCUMENT"})
    before = core_db.dump()
    with TestClient(create_app()) as client:
        url = f"/api/internal/runs/{run['id']}/otel"
        response = client.get(url, headers=headers())
        assert response.status_code == 200
        assert response.json() == client.get(url, headers=headers("REVIEWER")).json()
        assert "PRIVATE" not in response.text
        spans = response.json()["resourceSpans"][0]["scopeSpans"][0]["spans"]
        assert len(spans) == 3
        root, extract, blocked = spans
        assert len(root["traceId"]) == 32 and len(root["spanId"]) == 16
        assert extract["parentSpanId"] == blocked["parentSpanId"] == root["spanId"]
        assert all(int(span["endTimeUnixNano"]) >= int(span["startTimeUnixNano"]) for span in spans)
        assert blocked["status"]["code"] == 2
        assert any(a["key"] == "gen_ai.usage.input_tokens" and a["value"] == {"intValue": "12"} for a in extract["attributes"])
        assert client.get(url, headers=headers("BUYER")).status_code == 403
        assert client.get("/api/internal/runs/absent/otel", headers=headers()).status_code == 404
    assert core_db.dump() == before
