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
from pydantic import BaseModel, ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.models import AdmitResult, PassportResponse, PUBLIC_FIELDS
from app.api.contracts import CaseHistoryResponse, EventLogItem, ReviewResponse, RunResponse

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
def isolated_settings(mode: str, database: Path, *, replay_freeze: bool | None = None) -> Iterator[None]:
    from app import config
    overrides = {"DB_PATH": str(database), "LLM_MODE": mode, "WORKER_INLINE": "1",
                 "OCR_ENABLED": "0", "WEB_SEARCH": "off", "AGENTS_TRACING": "0",
                 "OPENAI_AGENTS_DISABLE_TRACING": "1", "DEMO_RUN_DELAY_S": "0"}
    if replay_freeze is not None:
        overrides["REPLAY_FREEZE"] = "1" if replay_freeze else "0"
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


class StoredField(BaseModel):
    id: str
    field_key: str
    result_version: int
    case_revision: int
    verdict: str
    conflict_locus: str | None
    review_state: str
    seller_attributable: bool
    citations_json: str
    explain_json: str


@dataclass(frozen=True)
class CaseState:
    revision: int
    fields: dict[str, StoredField]
    stale_trace_zero_calls: bool
    injection_flagged: bool
    unreadable_claim: bool


def case_state(path: Path, case_id: str) -> CaseState:
    """Read-only assertion seam; never manufactures an event, run or finding."""
    with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        case = connection.execute("SELECT revision FROM cases WHERE id=?", (case_id,)).fetchone()
        if case is None:
            raise CheckFailure("scenario case is missing")
        fields = {row["field_key"]: StoredField.model_validate(dict(row)) for row in connection.execute(
            "SELECT * FROM field_results WHERE case_id=? AND superseded_by IS NULL", (case_id,))}
        steps = list(connection.execute("SELECT t.* FROM trace_steps t WHERE t.run_id=(SELECT id FROM runs "
            "WHERE case_id=? ORDER BY case_revision DESC,created_at DESC,id DESC LIMIT 1)", (case_id,)))
        stale = [row for row in steps if row["step"] == "stale:mark"]
        flagged = any(isinstance(detail := json.loads(row["detail"] or "{}"), dict)
                      and detail.get("ignored_instructions_detected") is True for row in steps)
        unreadable = connection.execute("SELECT 1 FROM claims c JOIN source_versions v ON v.id=c.source_version_id "
            "JOIN sources s ON s.id=v.source_id WHERE s.case_id=? AND v.is_current=1 "
            "AND c.readability='UNREADABLE' LIMIT 1", (case_id,)).fetchone() is not None
    return CaseState(int(case["revision"]), fields,
        bool(stale) and all(row["actor"] == "code" and row["tokens_in"] == 0 and row["tokens_out"] == 0
                           for row in stale), flagged, unreadable)


def run_phase_two(client: httpx.Client, state: Callable[[str], CaseState], counts: Callable[[], dict[str, int]],
                  product_id: str, case_id: str, hydra_product: str, hydra_case: str,
                  claims_product: str, claims_case: str, *, expected_mode: str = "fallback") -> list[Check]:
    """Continue the S1 state in the documented 05→06→04→review→07→10→11→13 order."""
    checks: list[Check] = []
    stage = "05-revoke-notification"

    def fire(name: str, expected_case: str = case_id) -> AdmitResult:
        before_runs = {RunResponse.model_validate(row).id for row in successful(client.get(
            "/api/internal/runs", headers=HEADERS["OPERATOR"])).json()}
        result = AdmitResult.model_validate(successful(client.post(
            f"/api/internal/demo/fire/{name}", headers=HEADERS["OPERATOR"])).json())
        require(result.outcome == "ADMITTED" and result.job_id is not None,
                f"{name}: expected ADMITTED with a job, got {result.outcome}")
        new_runs = [run for row in successful(client.get("/api/internal/runs", headers=HEADERS["OPERATOR"])).json()
                    if (run := RunResponse.model_validate(row)).id not in before_runs]
        require(len(new_runs) == 1 and new_runs[0].case_id == expected_case,
                f"{name}: admitted event must produce one new run for its case")
        events = [EventLogItem.model_validate(row) for row in successful(client.get(
            "/api/internal/events/log", headers=HEADERS["OPERATOR"])).json()]
        require(any(item.event_id == result.event_id and item.job_id == result.job_id
                    and item.run_id == new_runs[0].id for item in events), "event/job/run linkage missing")
        return result

    def passport(product: str) -> PassportResponse:
        return PassportResponse.model_validate(successful(client.get(
            f"/api/products/{product}/passport", headers=HEADERS["REVIEWER"])).json())

    def history(case: str) -> CaseHistoryResponse:
        return CaseHistoryResponse.model_validate(successful(client.get(
            f"/api/cases/{case}/history", headers=HEADERS["REVIEWER"])).json())

    try:
        identifiers = {"notification_number", "responsible_company"}
        before = state(case_id)
        result = fire(stage)
        require(set(result.stale_fields) == identifiers, "revoke must stale only the two dependent fields")
        after = state(case_id)
        require(after.stale_trace_zero_calls, "stale marking must be traced as code with zero model tokens")
        observed = {field.field_key: field for field in passport(product_id).fields}
        require(all(observed[key].verdict == "INSUFFICIENT" and observed[key].freshness == "CURRENT"
                    for key in identifiers), "re-assessment must mark notification fields INSUFFICIENT/CURRENT")
        require(all(after.fields[key].result_version == before.fields[key].result_version
                    for key in set(PUBLIC_FIELDS) - identifiers), "revoke changed an unrelated result version")
        requests = [item for item in history(case_id).requests if item.status == "OPEN"]
        require({item.field_key for item in requests} == identifiers and len(requests) == 2,
                "revoke must open exactly two evidence requests")
        request_ids = {item.id for item in requests}
        checks.append(Check(stage, "PASS", "selective stale; code-only mark; two requests"))

        stage = "06-evidence-added"
        fire(stage)
        observed = {field.field_key: field for field in passport(product_id).fields}
        require(observed["responsible_company"].verdict == "CONSISTENT" and
                observed["notification_number"].verdict == "CONFLICTING", "new document results differ")
        fulfilled = {item.id for item in history(case_id).requests if item.status == "FULFILLED"}
        require(request_ids <= fulfilled, "the two original requests must be FULFILLED")
        checks.append(Check(stage, "PASS", "company CONSISTENT; number CONFLICTING; requests fulfilled"))

        stage = "04-volume-change"
        prior = state(case_id).fields["volume"]
        fire(stage)
        current = state(case_id)
        volume = current.fields["volume"]
        require(volume.verdict == "CONFLICTING" and volume.conflict_locus == "LISTING_VS_SOURCE",
                "volume must conflict against reference")
        checks.append(Check(stage, "PASS", "CONFLICTING / LISTING_VS_SOURCE"))

        stage = "review and stale revision"
        review = ReviewResponse.model_validate(successful(client.post(f"/api/cases/{case_id}/reviews",
            headers=HEADERS["REVIEWER"], json={"result_id": volume.id, "case_revision": current.revision,
                "decision": "APPROVE", "reason": "Review the current cited result"})).json())
        require(review.result_id == volume.id and review.case_revision == current.revision and
                review.decision == "APPROVE" and review.review_state == "REVIEWED", "review binding/state mismatch")
        require(any(item.id == review.id for item in history(case_id).reviews), "review missing from history")
        before_counts = counts()
        rejected = client.post(f"/api/cases/{case_id}/reviews", headers=HEADERS["REVIEWER"], json={
            "result_id": prior.id, "case_revision": prior.case_revision, "decision": "APPROVE",
            "reason": "Review of the prior revision"})
        require(rejected.status_code == 409, f"stale review: HTTP {rejected.status_code}, expected 409")
        require(counts() == before_counts, "rejected stale review changed persistent state")
        checks.append(Check(stage, "PASS", "review listed; stale revision 409 without writes"))

        stage = "07-injection-listing"
        fire(stage)
        current = state(case_id)
        require(current.fields["volume"].verdict == "CONSISTENT" and current.injection_flagged,
                "volume must recover and source instructions must be flagged")
        checks.append(Check(stage, "PASS", "volume CONSISTENT; instructions flagged"))

        stage = "10-blurred-label-photo"
        before_verdicts = {key: value.verdict for key, value in current.fields.items() if key in PUBLIC_FIELDS}
        fire(stage)
        current = state(case_id)
        require(current.unreadable_claim, "blurred label must retain UNREADABLE provenance")
        require({key: value.verdict for key, value in current.fields.items() if key in PUBLIC_FIELDS} == before_verdicts,
                "blurred upload must not erase existing readable support")
        checks.append(Check(stage, "PASS", "UNREADABLE; existing readable support retained"))

        stage = "11-bootstrap-hydra"
        fire(stage, hydra_case)
        current = state(hydra_case)
        observed = {field.field_key: field for field in passport(hydra_product).fields}
        for key in ("skin_type", "key_ingredients"):
            field = current.fields[key]
            require(field.verdict == "CONFLICTING" and field.conflict_locus == "WITHIN_SOURCE"
                    and field.review_state == "NEEDS_REVIEW" and not field.seller_attributable,
                    f"{key}: expected within-source conflict without seller attribution")
            require(observed[key].label == "Conflict in source" and len(observed[key].citations) >= 2,
                    f"{key}: source-conflict label/citations missing")
        checks.append(Check(stage, "PASS", "two cited source conflicts without seller attribution"))

        stage = "13-bootstrap-clear-serum"
        fire(stage, claims_case)
        findings = [value for key, value in state(claims_case).fields.items() if key.startswith("claim:")]
        require(sum(field.verdict == "CONFLICTING" for field in findings) >= 2, "expected at least two claim conflicts")
        for field in findings:
            require(field.review_state == "NEEDS_REVIEW" and bool(json.loads(field.citations_json))
                    and any(str(step.get("rule", "")).startswith("CL") for step in json.loads(field.explain_json)),
                    "claim finding must have citations, CL trail and reviewer state")
        buyer = PassportResponse.model_validate(successful(client.get(
            f"/api/products/{claims_product}/passport", headers=HEADERS["BUYER"])).json())
        require(all(not field.field_key.startswith("claim:") for field in buyer.fields), "buyer received expert claim findings")
        checks.append(Check(stage, "PASS", "cited policy claim findings; buyer details filtered"))

        stage = "S2 run modes"
        runs = [RunResponse.model_validate(row) for row in successful(client.get(
            "/api/internal/runs", headers=HEADERS["OPERATOR"])).json()]
        require(bool(runs) and all(run.llm_mode == expected_mode.upper() and
                                 run.status in {"COMPLETED", "WAITING_REVIEW", "WAITING_EVIDENCE"}
                                 and run.stop_reason is None for run in runs), "S2 run mode/status/stop differs")
        checks.append(Check(stage, "PASS", expected_mode.upper()))
    except (CheckFailure, ValidationError, KeyError, ValueError) as error:
        checks.append(Check(stage, "FAIL", str(error)))
    return checks


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", type=int, choices=(1, 2, 3, 4))
    parser.add_argument("--mode", choices=("fallback", "replay"))
    args = parser.parse_args(argv)
    mode = args.mode if args.mode is not None else os.getenv("LLM_MODE", "fallback")
    if mode not in {"fallback", "replay"}:
        parser.error("select fallback or replay; record/live are not supported by the offline gate")
    if args.phase not in {1, 2}:
        parser.error("only phase-1/2 paths are implemented; later phases must extend this gate before use")
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
                if args.phase == 2 and all(check.status == "PASS" for check in checks):
                    required = ("05-revoke-notification", "06-evidence-added", "04-volume-change",
                                "07-injection-listing", "10-blurred-label-photo", "11-bootstrap-hydra",
                                "13-bootstrap-clear-serum")
                    missing = [name for name in required if not (config.settings.fixtures_dir / "events" / (name + ".json")).exists()]
                    if missing:
                        checks.append(Check("S2 fixtures", "SKIP", "missing: " + ", ".join(missing)))
                    else:
                        with closing(sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)) as connection:
                            def scenario(name: str) -> tuple[str, str]:
                                event = json.loads((config.settings.fixtures_dir / "events" / (name + ".json")).read_text(encoding="utf-8"))
                                product = str(event["payload"]["product_id"])
                                row = connection.execute("SELECT id FROM cases WHERE product_id=?", (product,)).fetchone()
                                if row is None:
                                    raise CheckFailure("fixture product has no seeded case")
                                return product, str(row[0])
                            _, case_id = scenario("01-bootstrap-demo")
                            hydra_product, hydra_case = scenario("11-bootstrap-hydra")
                            claims_product, claims_case = scenario("13-bootstrap-clear-serum")
                        checks.extend(run_phase_two(client, lambda case: case_state(database, case),
                            lambda: table_counts(database), product_id, case_id, hydra_product, hydra_case,
                            claims_product, claims_case, expected_mode=mode))
            if network_attempts:
                checks.append(Check("network", "FAIL", "model network call attempted"))
    print("check | status | detail")
    for check in checks:
        print(f"{check.name} | {check.status} | {check.detail}")
    return int(any(check.status != "PASS" for check in checks))


if __name__ == "__main__":
    raise SystemExit(main())
