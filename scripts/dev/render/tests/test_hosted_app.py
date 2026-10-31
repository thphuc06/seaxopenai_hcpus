"""Deployment-only tests; exercise the real API composition with a temporary DB."""
from collections.abc import Iterator
from pathlib import Path
import sqlite3
import sys
from contextlib import closing

from fastapi.testclient import TestClient
import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
from app import config
from scripts.dev.render.server import create_hosted_app


@pytest.fixture
def hosted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><body>Deployment preview</body></html>", encoding="utf-8")
    (dist / "assets").mkdir()
    (dist / "assets/app.js").write_text("export const ready = true;", encoding="utf-8")
    (tmp_path / "private.txt").write_text("outside asset root", encoding="utf-8")
    try:
        with monkeypatch.context() as env:
            env.setenv("DB_PATH", str(tmp_path / "app.db"))
            env.setenv("LLM_MODE", "fallback")
            env.setenv("WORKER_INLINE", "1")
            env.setenv("OCR_ENABLED", "0")
            config.reload_settings()
            with TestClient(create_hosted_app(dist)) as client:
                yield client
    finally:
        config.reload_settings()


def test_real_health_and_frontend_reads_do_not_create_run(hosted: TestClient) -> None:
    with closing(sqlite3.connect(config.settings.db_path)) as db:
        before = db.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        assert hosted.get("/api/health").json()["llm_mode"] == "fallback"
        for path in ("/", "/buyer/one", "/reviewer/unseen-product"):
            response = hosted.get(path)
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/html")
            assert "Deployment preview" in response.text
        assert db.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == before


def test_assets_and_head(hosted: TestClient) -> None:
    response = hosted.get("/assets/app.js")
    assert response.status_code == 200
    assert "export const ready" in response.text
    assert hosted.head("/buyer/one").status_code == 200
    assert hosted.head("/buyer/one").content == b""


@pytest.mark.parametrize("path", [
    "/api/unknown", "/api", "/assets/missing.js", "/assets/missing",
    "/missing.png", "/.env", "/%2e%2e/private.txt", "/assets/%2e%2e/%2e%2e/private.txt",
])
def test_missing_api_assets_and_outside_paths_never_return_spa(hosted: TestClient, path: str) -> None:
    response = hosted.get(path)
    assert response.status_code == 404
    assert "Deployment preview" not in response.text
    assert "outside asset root" not in response.text


def test_mutating_frontend_request_rejected(hosted: TestClient) -> None:
    assert hosted.post("/buyer/one").status_code == 405


def test_missing_build_is_explicit(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="Frontend build missing"):
        create_hosted_app(tmp_path)
