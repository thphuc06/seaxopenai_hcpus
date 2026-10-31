"""Offline in-process check of built image assets, API startup and excluded labels."""
from pathlib import Path
import tempfile

from fastapi.testclient import TestClient

from app import config
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
        finally:
            config.settings.db_path = original
    print("Image check passed: startup, assets, SPA route, API 404 and excluded labels")


if __name__ == "__main__":
    main()
