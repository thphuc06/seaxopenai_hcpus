"""Offline in-process check of built image assets, API startup and excluded labels."""
from pathlib import Path
from contextlib import closing
import json
import tempfile

from fastapi.testclient import TestClient

from app import config, db
from scripts.dev.render.server import REPO_ROOT, create_hosted_app


def main() -> None:
    assert not (REPO_ROOT / "backend/.env").exists(), "Local env leaked into image"
    assert not (REPO_ROOT / "fixtures/gold").exists(), "Offline labels leaked into image"
    assert not (REPO_ROOT / "fixtures/blind").exists(), "Blind dataset leaked into image"
    original = config.settings.db_path
    with tempfile.TemporaryDirectory() as folder:
        config.settings.db_path = Path(folder) / "image-check.db"
        try:
            with TestClient(create_hosted_app()) as client:
                health = client.get("/api/health")
                assert health.status_code == 200
                assert health.json()["llm_mode"] == "fallback"
                assert client.get("/").status_code == 200
                assert client.get("/buyer/preview").status_code == 200
                assert client.get("/api/unknown-route").status_code == 404
                assert client.get("/assets/missing.js").status_code == 404
                with closing(db.connect()) as connection:
                    before = list(connection.iterdump())
                expected = json.loads((REPO_ROOT / "docs/results/metrics.json").read_text(encoding="utf-8"))
                assert expected["available"] is True
                for role in ("REVIEWER", "OPERATOR"):
                    response = client.get("/api/internal/eval/metrics", headers={"X-Demo-Role": role, "X-Demo-Actor": "image-check"})
                    assert response.status_code == 200 and response.json() == expected
                assert client.get("/api/internal/eval/metrics", headers={"X-Demo-Role": "BUYER", "X-Demo-Actor": "image-check"}).status_code == 403
                with closing(db.connect()) as connection:
                    assert list(connection.iterdump()) == before
        finally:
            config.settings.db_path = original
    print("Image check passed: startup, assets, SPA route, API 404, read-only scorecard with ACL/provenance and excluded labels")


if __name__ == "__main__":
    main()
