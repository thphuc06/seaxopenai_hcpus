"""Offline test setup shared by all lanes; P4 owns phase gating."""
from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import closing
from importlib import import_module
from importlib.util import find_spec
import os
from pathlib import Path
import re
import sqlite3
import subprocess

import pytest
from _pytest.terminal import TerminalReporter
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


def pytest_terminal_summary(terminalreporter: TerminalReporter) -> None:
    """Annotate cross-lane failures without changing any test outcome or gate."""
    lane = os.getenv("CONTEST_LANE", "").upper()
    if not lane:
        branch = subprocess.run(
            ["git", "branch", "--show-current"], cwd=Path(__file__).resolve().parents[2],
            check=True, capture_output=True, text=True, encoding="utf-8",
        ).stdout.strip()
        match = re.fullmatch(r"p([1-4])(?:-b\d+)?", branch)
        lane = f"P{match.group(1)}" if match else ""
    if lane not in {"P1", "P2", "P3", "P4"}:
        return
    session = terminalreporter._session
    if session is None:
        return
    items = {item.nodeid: item for item in session.items}
    reported: set[str] = set()
    for category in ("failed", "error"):
        for report in terminalreporter.stats.get(category, []):
            item = items.get(report.nodeid)
            if item is None or report.nodeid in reported:
                continue
            dependencies = sorted({
                str(owner) for marker in item.iter_markers("needs") for owner in marker.args
                if str(owner) != lane
            })
            if dependencies:
                terminalreporter.write_line(
                    f"WAITING on {', '.join(dependencies)}: {report.nodeid} (still {category})"
                )
                reported.add(report.nodeid)


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
