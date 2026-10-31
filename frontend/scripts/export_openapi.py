"""Export the checked-out backend's /openapi.json without starting a server."""
from pathlib import Path
import json
import sys

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.main import create_app  # noqa: E402


def main() -> None:
    # No context-manager entry: schema requests do not need startup/fixture seeding.
    client = TestClient(create_app())
    try:
        response = client.get("/openapi.json")
        response.raise_for_status()
        schema = response.json()
    finally:
        client.close()
    destination = ROOT / "frontend/node_modules/.cache/contract-openapi.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Exported {len(schema['paths'])} paths from the local backend OpenAPI.")


if __name__ == "__main__":
    main()
