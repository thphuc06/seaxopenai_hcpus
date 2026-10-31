"""Offline test setup shared by all lanes; P4 owns phase gating."""
from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import closing
from importlib import import_module
from importlib.util import find_spec
import os
from pathlib import Path
import sqlite3

import pytest
from fastapi.testclient import TestClient
from httpx import Response

os.environ.setdefault("LLM_MODE", "fallback")
os.environ.setdefault("WORKER_INLINE", "1")
os.environ.setdefault("OCR_ENABLED", "0")

from app import config
from app.main import create_app
from app.models import PassportField, PassportResponse, Role

HEADERS = {role.value: {"X-Demo-Role": role.value, "X-Demo-Actor": f"test-{role.value.lower()}"} for role in Role}
BUYER = HEADERS["BUYER"]
SELLER = HEADERS["SELLER"]
REVIEWER = HEADERS["REVIEWER"]
OPERATOR = HEADERS["OPERATOR"]
SYSTEM = HEADERS["SYSTEM"]


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    phase = int(os.getenv("CONTEST_PHASE") or Path(__file__).with_name("PHASE").read_text(encoding="utf-8").strip())
    for item in items:
        marker = item.get_closest_marker("phase")
        if marker and int(marker.args[0]) > phase:
            item.add_marker(pytest.mark.skip(reason=f"Requires phase {marker.args[0]}; current phase {phase}"))


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    # Environment is the documented configuration seam; never patch app behavior.
    try:
        with monkeypatch.context() as env:
            env.setenv("DB_PATH", str(tmp_path / "test.db"))
            env.setenv("REPLAY_DIR", str(tmp_path / "replay"))
            env.setenv("LLM_MODE", "fallback")
            env.setenv("WORKER_INLINE", "1")
            env.setenv("OCR_ENABLED", "0")
            config.reload_settings()
            with TestClient(create_app()) as test_client:
                if find_spec("app.seed") is not None:
                    import_module("app.seed").reset()
                yield test_client
    finally:
        config.reload_settings()


@pytest.fixture
def fire(client: TestClient) -> Callable[[str], Response]:
    def submit(name: str) -> Response:
        return client.post(f"/api/internal/demo/fire/{name}", headers=OPERATOR)
    return submit


@pytest.fixture
def passport(client: TestClient) -> Callable[[str, str], PassportResponse]:
    def read(product_id: str, role: str = "BUYER") -> PassportResponse:
        response = client.get(f"/api/products/{product_id}/passport", headers=HEADERS[role])
        response.raise_for_status()
        return PassportResponse.model_validate(response.json())
    return read


@pytest.fixture
def fields() -> Callable[[PassportResponse], dict[str, PassportField]]:
    return lambda p: {item.field_key: item for item in p.fields}


@pytest.fixture
def counts(client: TestClient) -> Callable[[], dict[str, int]]:
    def snapshot() -> dict[str, int]:
        path = config.settings.db_path
        if not path.exists():
            raise RuntimeError("P1 storage is required for counts()")
        with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as db:
            return {
                table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in ("events", "runs", "trace_steps", "field_results", "gaps", "claims")
            }
    return snapshot
