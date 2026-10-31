"""In-process, isolated phase click path. No server or network is required."""
from __future__ import annotations

import argparse
from collections.abc import Callable, Iterator, Sequence
from contextlib import closing, contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.models import AdmitResult, PassportResponse, PUBLIC_FIELDS
from app.api.contracts import RunResponse

HEADERS = {role: {"X-Demo-Role": role, "X-Demo-Actor": "sync-check"}
           for role in ("BUYER", "REVIEWER", "OPERATOR")}


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str


class CheckFailure(Exception):
    """An observed response does not satisfy the documented story."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CheckFailure(message)


def successful(response: httpx.Response) -> httpx.Response:
    require(response.is_success, f"{response.request.method} {response.request.url.path}: HTTP {response.status_code}")
    return response


def table_counts(path: Path) -> dict[str, int]:
    with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as db:
        tables = [row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )]
        return {name: db.execute('SELECT COUNT(*) FROM "' + name.replace('"', '""') + '"').fetchone()[0]
                for name in tables}


def run_phase_one(client: httpx.Client, counts: Callable[[], dict[str, int]],
                  product_id: str, excluded_passages: Callable[[], set[str]] = set,
                  *, expected_mode: str = "fallback") -> list[Check]:
    """HTTP client and read-only counters are the replaceable external seams."""
    checks: list[Check] = []
    stage = "reset"
    try:
        successful(client.post("/api/internal/demo/reset", headers=HEADERS["OPERATOR"]))
        checks.append(Check(stage, "PASS", "isolated demo state reset"))
        stage = "01-bootstrap-demo"
        result = AdmitResult.model_validate(successful(client.post(
            f"/api/internal/demo/fire/{stage}", headers=HEADERS["OPERATOR"],
        )).json())
        require(result.outcome == "ADMITTED" and result.job_id is not None, "bootstrap must admit one job")
        checks.append(Check(stage, "PASS", result.outcome))
        stage = "bootstrap run mode/status"
        runs_payload = successful(client.get("/api/internal/runs", headers=HEADERS["OPERATOR"])).json()
        require(isinstance(runs_payload, list) and len(runs_payload) == 1, "bootstrap must produce one run")
        run = RunResponse.model_validate(runs_payload[0])
        require(run.llm_mode == expected_mode.upper(), f"run mode {run.llm_mode}, expected {expected_mode.upper()}")
        require(run.status == "COMPLETED" and run.stop_reason is None,
                f"run status {run.status}, stop_reason={run.stop_reason}")
        checks.append(Check(stage, "PASS", f"{run.llm_mode} {run.status}"))
        for role in ("BUYER", "REVIEWER"):
            stage = f"{role} passport"
            passport = PassportResponse.model_validate(successful(client.get(
                f"/api/products/{product_id}/passport", headers=HEADERS[role],
            )).json())
            fields = {field.field_key: field for field in passport.fields}
            require(set(fields) == set(PUBLIC_FIELDS), "five public fields required")
            for key, field in fields.items():
                expected = "SINGLE_SOURCE" if key == "skin_type" else "CONSISTENT"
                require(field.verdict == expected, f"{key}: {field.verdict}, expected {expected}")
                require(field.freshness == "CURRENT", f"{key}: {field.freshness}")
                if role == "REVIEWER":
                    require(bool(field.citations), f"{key}: no citation")
                    require(not excluded_passages().intersection(c.passage_id for c in field.citations),
                            f"{key}: cited a source from another market")
                checks.append(Check(f"{role} {key}", "PASS", field.verdict))
        for name, expected in (("02-price-change", "NOOP"),
                               ("03-duplicate-price-change", "DUPLICATE"),
                               ("08-rejected-producer", "REJECTED")):
            stage = name
            before = counts()
            event_metrics_before = successful(client.get("/api/internal/metrics", headers=HEADERS["OPERATOR"])).json()
            result = AdmitResult.model_validate(successful(client.post(
                f"/api/internal/demo/fire/{name}", headers=HEADERS["OPERATOR"],
            )).json())
            require(result.outcome == expected, f"{result.outcome}, expected {expected}")
            after = counts()
            if expected != "DUPLICATE":
                require(result.job_id is None, "non-admitted event created a job")
                require(after.pop("events") == before.pop("events") + 1, "event was not recorded once")
            require(after == before, "unexpected persistent side effects")
            event_metrics_after = successful(client.get("/api/internal/metrics", headers=HEADERS["OPERATOR"])).json()
            for counter in ("jobs", "runs", "model_calls"):
                require(event_metrics_after[counter] == event_metrics_before[counter], f"{expected} changed {counter}")
            checks.append(Check(stage, "PASS", expected))
        stage = "buyer reads x3"
        before = counts()
        metrics_before = successful(client.get("/api/internal/metrics", headers=HEADERS["OPERATOR"])).json()
        for _ in range(3):
            successful(client.get(f"/api/products/{product_id}/passport", headers=HEADERS["BUYER"]))
        metrics_after = successful(client.get("/api/internal/metrics", headers=HEADERS["OPERATOR"])).json()
        require(counts() == before, "buyer read created rows")
        for counter in ("jobs", "runs", "model_calls", "events"):
            require(metrics_after[counter] == metrics_before[counter], f"buyer read changed {counter}")
        checks.append(Check(stage, "PASS", "no jobs, runs, events or model calls"))
    except (CheckFailure, ValidationError, KeyError, ValueError) as error:
        checks.append(Check(stage, "FAIL", str(error)))
    return checks


@contextmanager
def isolated_settings(mode: str, database: Path) -> Iterator[None]:
    from app import config
    overrides = {"DB_PATH": str(database), "LLM_MODE": mode, "WORKER_INLINE": "1",
                 "OCR_ENABLED": "0", "WEB_SEARCH": "off", "AGENTS_TRACING": "0",
                 "OPENAI_AGENTS_DISABLE_TRACING": "1", "DEMO_RUN_DELAY_S": "0"}
    previous = {name: os.environ.get(name) for name in overrides}
    try:
        os.environ.update(overrides)
        config.reload_settings()
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        config.reload_settings()


def wrong_market_passages(path: Path, product_id: str) -> set[str]:
    with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as db:
        return {row[0] for row in db.execute(
            "SELECT p.id FROM passages p JOIN source_versions sv ON sv.id=p.source_version_id "
            "JOIN sources s ON s.id=sv.source_id JOIN products product ON product.id=s.product_id "
            "WHERE product.id=? AND json_extract(sv.scope_json, '$.market') != product.market", (product_id,),
        )}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", type=int, choices=(1, 2, 3, 4))
    parser.add_argument("--mode", choices=("fallback", "replay"))
    args = parser.parse_args(argv)
    mode = args.mode if args.mode is not None else os.getenv("LLM_MODE", "fallback")
    if mode not in {"fallback", "replay"}:
        parser.error("select fallback or replay; record/live are not supported by the offline gate")
    if args.phase != 1:
        parser.error("only the phase-1 path is implemented; later phases must extend this gate before use")
    print(f"phase={args.phase} mode={mode}")
    from app import config
    from app.main import create_app
    bootstrap = config.settings.fixtures_dir / "events/01-bootstrap-demo.json"
    if not bootstrap.exists():
        print("bootstrap | SKIP | required source fixture is missing; gate incomplete")
        return 1
    product_id = json.loads(bootstrap.read_text(encoding="utf-8"))["payload"]["product_id"]
    with TemporaryDirectory(prefix="passport-sync-") as directory:
        database = Path(directory) / "check.db"
        network_attempts: list[str] = []

        def deny_network(**request: object) -> None:
            network_attempts.append("model")
            raise CheckFailure("offline gate attempted a network model call")

        with isolated_settings(mode, database), patch("app.llm.client._call_api", deny_network):
            with TestClient(create_app()) as client:
                checks = run_phase_one(client, lambda: table_counts(database), product_id,
                                       lambda: wrong_market_passages(database, product_id), expected_mode=mode)
            if network_attempts:
                checks.append(Check("network", "FAIL", "model network call attempted"))
    print("check | status | detail")
    for check in checks:
        print(f"{check.name} | {check.status} | {check.detail}")
    return int(any(check.status != "PASS" for check in checks))


if __name__ == "__main__":
    raise SystemExit(main())
