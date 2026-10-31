"""In-process, isolated phase click path. No server or network is required."""
from __future__ import annotations

import argparse
from collections.abc import Callable, Iterator, Sequence
from contextlib import closing, contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from pydantic import BaseModel, JsonValue, ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.models import AdmitResult, PassportResponse, PUBLIC_FIELDS
from app.api.contracts import CaseHistoryResponse, EventLogItem, ReviewResponse, RunResponse
from app.api.s4_contracts import (BuyerMarketplaceResponse, ExpertMarketplaceResponse,
                                MarketplaceScanResponse, ReceiptResponse, WebAuditResponse)

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


class ScopeProbe(BaseModel):
    scope_match: str
    decided_by: str
    anchor_passage_id: str | None


class PhaseThreeProbe(BaseModel):
    mode: str
    status: str
    stop_reason: str | None
    scopes: list[ScopeProbe]
    effects: list[dict[str, JsonValue]]
    registry_closed: bool
    private_fragments: list[str]


def checked_scope_anchor(connection: sqlite3.Connection, placement: sqlite3.Row,
                         validations: list[dict[str, JsonValue]]) -> str | None:
    """Read a serialized code-verified PassageScope, never a raw agent proposal."""
    if placement["decided_by"] != "AGENT_VERIFIED":
        return None
    if not connection.execute("SELECT 1 FROM passages WHERE id=? AND source_version_id=?",
            (placement["passage_id"], placement["source_version_id"])).fetchone():
        return None
    anchors: set[str] = set()
    for detail in validations:
        if (detail.get("passage_id"), detail.get("sv_id"), detail.get("scope_match"), detail.get("decided_by")) != (
                placement["passage_id"], placement["source_version_id"], placement["scope_match"], "AGENT_VERIFIED"):
            continue
        anchor = detail.get("anchor_passage_id")
        if isinstance(anchor, str) and anchor != placement["passage_id"] and connection.execute(
                "SELECT 1 FROM passages WHERE id=? AND source_version_id=?",
                (anchor, placement["source_version_id"])).fetchone():
            anchors.add(anchor)
    return next(iter(anchors)) if len(anchors) == 1 else None


def scope_validation(connection: sqlite3.Connection, row: sqlite3.Row) -> dict[str, JsonValue]:
    """Normalize accepted producer refs; retain the earlier serialized placement form."""
    detail = json.loads(row["detail"] or "{}")
    if not isinstance(detail, dict):
        return {}
    if "accepted" not in detail:
        return detail
    if detail["accepted"] is not True or not {"input_refs", "output_refs"} <= set(row.keys()):
        return {}
    inputs = json.loads(row["input_refs"] or "[]")
    outputs = json.loads(row["output_refs"] or "[]")
    if not (isinstance(inputs, list) and isinstance(outputs, list) and len(inputs) == len(outputs) == 1
            and isinstance(inputs[0], str) and isinstance(outputs[0], str)):
        return {}
    target = connection.execute("SELECT source_version_id FROM passages WHERE id=?", (inputs[0],)).fetchall()
    if len(target) != 1:
        return {}
    return {"passage_id": inputs[0], "sv_id": target[0][0], "scope_match": detail.get("scope_match"),
            "decided_by": "AGENT_VERIFIED", "anchor_passage_id": outputs[0]}


def phase_three_probe(database: Path, case_id: str) -> PhaseThreeProbe:
    with closing(sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        run = connection.execute("SELECT * FROM runs WHERE case_id=? ORDER BY case_revision DESC,created_at DESC,id DESC LIMIT 1",
                                 (case_id,)).fetchone()
        if run is None:
            raise CheckFailure("phase3 run absent")
        steps = [(row["step"], json.loads(row["detail"] or "{}")) for row in connection.execute(
            "SELECT step,detail FROM trace_steps WHERE run_id=?", (run["id"],))]
        validations = [scope_validation(connection, row) for row in connection.execute(
            "SELECT * FROM trace_steps WHERE run_id=? AND step='scope:validate' AND actor='code' AND error IS NULL",
            (run["id"],)) if row["detail"]]
        scopes = [ScopeProbe(scope_match=row["scope_match"], decided_by=row["decided_by"],
                            anchor_passage_id=checked_scope_anchor(connection, row, validations))
                  for row in connection.execute(
                      "SELECT source_version_id,passage_id,scope_match,decided_by FROM passage_scopes WHERE run_id=?", (run["id"],))]
        source_passages = list(connection.execute(
            "SELECT p.text,p.id AS passage_id,sv.id AS version_id,s.id AS source_id,s.visibility "
            "FROM passages p JOIN source_versions sv ON sv.id=p.source_version_id "
            "JOIN sources s ON s.id=sv.source_id WHERE s.case_id=?", (case_id,)))
        public_texts = [str(row["text"]) for row in source_passages if row["visibility"] == "PUBLIC" and row["text"]]
        private: list[str] = []
        for row in source_passages:
            if row["visibility"] != "PRIVATE":
                continue
            private.extend(str(row[key]) for key in ("passage_id", "version_id", "source_id"))
            text = str(row["text"] or "")
            if text and not any(text in public for public in public_texts):
                private.append(text)
        for row in connection.execute("SELECT explain_json FROM field_results WHERE case_id=? AND superseded_by IS NULL", (case_id,)):
            private.extend(str(step["rule"]) for step in json.loads(row[0] or "[]") if step.get("rule"))
        private.extend(str(value) for value in (run["model"],) if value and value not in {"FALLBACK", "REPLAY"})
    return PhaseThreeProbe(mode=str(run["llm_mode"]).upper(), status=run["status"], stop_reason=run["stop_reason"], scopes=scopes,
        effects=[detail for name, detail in steps if name == "agent:effect"],
        registry_closed=any(name == "gap:stop" and detail.get("stop_reason") == "GAP_CLOSED" for name, detail in steps),
        private_fragments=private)


def run_phase_three(client: httpx.Client, state: Callable[[str], CaseState], counts: Callable[[], dict[str, int]],
                    probe: Callable[[str], PhaseThreeProbe], product_id: str, case_id: str,
                    sun_product: str, sun_case: str, *, expected_mode: str) -> list[Check]:
    checks: list[Check] = []
    stage = "09-catalogue-published"
    try:
        before_skin = state(case_id).fields["skin_type"].verdict
        result = AdmitResult.model_validate(successful(client.post(f"/api/internal/demo/fire/{stage}", headers=HEADERS["OPERATOR"])).json())
        require(result.outcome == "ADMITTED", "catalogue must be admitted")
        current = probe(case_id)
        require(current.mode == expected_mode.upper(), "catalogue run mode differs")
        require(current.stop_reason is None and current.status in {"COMPLETED", "WAITING_REVIEW"},
                f"{current.status}: {current.stop_reason}")
        require(any(row.decided_by == "CODE" and row.scope_match == "MATCH" for row in current.scopes), "no code MATCH")
        require(any(row.decided_by == "CODE" and row.scope_match == "MISMATCH" for row in current.scopes), "no code MISMATCH")
        if expected_mode == "fallback":
            require(any(row.scope_match == "UNKNOWN" for row in current.scopes), "size-less scope should remain unresolved")
            require(not any(row.decided_by == "AGENT_VERIFIED" for row in current.scopes), "fallback invented an agent placement")
            for effect in current.effects:
                if effect.get("before") != effect.get("after"):
                    provenance = effect.get("decided_by")
                    require(effect.get("before") is not None and effect.get("after") is not None
                            and isinstance(provenance, list) and bool(provenance)
                            and all(owner == "CODE" for owner in provenance), "fallback invented an agent effect")
        else:
            require(any(row.decided_by == "AGENT_VERIFIED" and row.scope_match == "MATCH" and row.anchor_passage_id
                        for row in current.scopes), "recorded code-checked anchor absent")
            require(state(case_id).fields["skin_type"].verdict != before_skin, "recorded agent did not change skin type")
            require(any(effect.get("before") is not None and effect.get("after") is not None and
                        effect["before"] != effect["after"] for effect in current.effects), "agent:effect before/after absent")
        checks.append(Check(stage, "PASS", expected_mode + " scope evidence"))
        stage = "12-bootstrap-sun-fluid"
        result = AdmitResult.model_validate(successful(client.post(f"/api/internal/demo/fire/{stage}", headers=HEADERS["OPERATOR"])).json())
        require(result.outcome == "ADMITTED", "registry scenario must be admitted")
        sun = probe(sun_case)
        require(sun.mode == expected_mode.upper() and sun.stop_reason is None and sun.status == "COMPLETED", "registry run incomplete/mode mismatch")
        if expected_mode == "replay":
            require(sun.registry_closed, "recorded registry GAP_CLOSED absent")
            require(all(state(sun_case).fields[key].verdict == "CONSISTENT" for key in
                        ("notification_number", "responsible_company")), "registry identifiers not supported")
        checks.append(Check(stage, "PASS", "registry scenario completed; closure independently checked in acceptance"))
        stage = "role-filtered explain"
        before_counts = counts()
        for product, case in ((product_id, case_id), (sun_product, sun_case)):
            forbidden = probe(case).private_fragments
            for field in PUBLIC_FIELDS:
                route = f"/api/products/{product}/fields/{field}/explain"
                buyer = successful(client.get(route, headers=HEADERS["BUYER"]))
                expert = successful(client.get(route, headers=HEADERS["REVIEWER"]))
                require(bool(buyer.json()) and bool(expert.json()), "empty explain response")
                buyer_values = json.dumps(buyer.json(), ensure_ascii=False)
                require(not any(fragment in buyer_values for fragment in forbidden), "buyer explain leaks private/internal detail")
        require(counts() == before_counts, "explain created persistent work")
        checks.append(Check(stage, "PASS", "buyer/expert projections; no added rows"))
    except (CheckFailure, ValidationError, KeyError, ValueError) as error:
        checks.append(Check(stage, "FAIL", str(error)))
    return checks


def s4_fire(client: httpx.Client, name: str, case_id: str, mode: str) -> None:
    before = {row["id"] for row in successful(client.get("/api/internal/runs", headers=HEADERS["OPERATOR"])).json()}
    admission = AdmitResult.model_validate(successful(client.post(
        f"/api/internal/demo/fire/{name}", headers=HEADERS["OPERATOR"])).json())
    require(admission.outcome == "ADMITTED" and admission.job_id is not None, f"{name}: no admitted job")
    runs = [RunResponse.model_validate(row) for row in successful(client.get(
        "/api/internal/runs", headers=HEADERS["OPERATOR"])).json() if row["id"] not in before]
    require(len(runs) == 1 and runs[0].case_id == case_id, "event must produce exactly one case run")
    run = runs[0]
    require(run.llm_mode == mode.upper() and run.stop_reason is None and
            run.status in {"COMPLETED", "WAITING_REVIEW", "WAITING_EVIDENCE"}, "run mode/status/stop mismatch")
    events = [EventLogItem.model_validate(row) for row in successful(client.get(
        "/api/internal/events/log", headers=HEADERS["OPERATOR"])).json()]
    require(any(row.event_id == admission.event_id and row.job_id == admission.job_id and row.run_id == run.id
                for row in events), "event/job/run linkage missing")


def s4_passport(client: httpx.Client, product: str) -> PassportResponse:
    passport = PassportResponse.model_validate(successful(client.get(
        f"/api/products/{product}/passport", headers=HEADERS["BUYER"])).json())
    require(passport.product_id == product, "passport belongs to another product")
    return passport


def stored_receipt(database: Path, receipt_id: str) -> tuple[str, str]:
    with closing(sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)) as connection:
        row = connection.execute("SELECT snapshot_json,snapshot_hash FROM orders WHERE id=?", (receipt_id,)).fetchone()
    require(row is not None, "receipt is not stored")
    return str(row[0]), str(row[1])


def check_receipt(client: httpx.Client, counts: Callable[[], dict[str, int]],
                  product: str, case: str, mode: str, stored: Callable[[str], tuple[str, str]]) -> None:
    successful(client.post("/api/internal/demo/reset", headers=HEADERS["OPERATOR"]))
    require(all(counts().get(table, 0) == 0 for table in ("orders", "events", "runs")), "receipt scenario is not fresh")
    s4_fire(client, "01-bootstrap-demo", case, mode)
    purchased = s4_passport(client, product)
    receipt = ReceiptResponse.model_validate(successful(client.post(
        "/api/orders", headers=HEADERS["BUYER"], json={"product_id": product})).json())
    require(receipt.product_id == product and receipt.case_id == case and receipt.snapshot == purchased,
            "receipt does not freeze the public purchase passport")
    require(receipt.hash_valid and bool(receipt.snapshot_hash) and bool(receipt.chain_head), "receipt hash/chain absent or invalid")
    original_row = stored(receipt.id)
    raw_snapshot, stored_hash = original_row
    require(hashlib.sha256(raw_snapshot.encode("utf-8")).hexdigest() == stored_hash == receipt.snapshot_hash,
            "receipt hash does not cover stored snapshot bytes")
    require(PassportResponse.model_validate_json(raw_snapshot) == purchased, "stored receipt differs from buyer snapshot")
    require(not receipt.changed_since_purchase and not any(row.changed for row in receipt.diff), "new receipt reports a change")
    s4_fire(client, "05-revoke-notification", case, mode)
    current = s4_passport(client, product)
    before_reads = counts()
    after = ReceiptResponse.model_validate(successful(client.get(f"/api/orders/{receipt.id}", headers=HEADERS["BUYER"])).json())
    immutable = ("id", "product_id", "case_id", "placed_at", "case_revision", "snapshot", "snapshot_hash", "chain_head")
    require(all(getattr(after, key) == getattr(receipt, key) for key in immutable), "purchase evidence was rewritten")
    require(after.hash_valid and after.changed_since_purchase, "receipt hash/diff invalid after revoke")
    require(stored(receipt.id) == original_row, "stored purchase evidence was rewritten")
    require(len(after.diff) == len(PUBLIC_FIELDS) and {row.field_key for row in after.diff} == set(PUBLIC_FIELDS), "receipt diff omits/duplicates fields")
    require(all(row.changed == (row.then != row.now) for row in after.diff), "receipt change flags disagree with full field diff")
    require({row.field_key for row in after.diff
             if (row.then.model_dump(exclude={"checked_at"}) if row.then else None) !=
                (row.now.model_dump(exclude={"checked_at"}) if row.now else None)} ==
            {"notification_number", "responsible_company"}, "receipt must change only the two dependent fields' content")
    original_fields = {row.field_key: row for row in purchased.fields}
    current_fields = {row.field_key: row for row in current.fields}
    require(all(row.then == original_fields[row.field_key] and row.now == current_fields[row.field_key]
                for row in after.diff), "receipt diff values disagree with then/now passports")
    listing = [ReceiptResponse.model_validate(row) for row in successful(client.get("/api/orders", headers=HEADERS["BUYER"])).json()]
    require(any(row.id == receipt.id and row.snapshot == purchased for row in listing), "receipt absent from buyer list")
    require(counts() == before_reads, "receipt GET created work")
    duplicate = AdmitResult.model_validate(successful(client.post(
        "/api/internal/demo/fire/05-revoke-notification", headers=HEADERS["OPERATOR"])).json())
    require(duplicate.outcome == "DUPLICATE" and counts() == before_reads, "second revoke created new work")


def check_marketplace(client: httpx.Client, counts: Callable[[], dict[str, int]],
                      product: str, case: str, bootstrap: str, mode: str) -> None:
    successful(client.post("/api/internal/demo/reset", headers=HEADERS["OPERATOR"]))
    s4_fire(client, bootstrap, case, mode)
    passport = s4_passport(client, product)
    scan = MarketplaceScanResponse.model_validate(successful(client.post(
        f"/api/internal/marketplace/{product}/scan", headers=HEADERS["OPERATOR"])).json())
    require(scan.product_id == product and scan.llm_mode == mode.upper() and scan.stop_reason is None,
            "marketplace scan mode/identity/stop mismatch")
    require(scan.sellers_processed > 0 and bool(scan.scan_id), "marketplace scan processed no seller")
    require(s4_passport(client, product) == passport, "marketplace scan changed the case passport")
    before = counts()
    buyer = BuyerMarketplaceResponse.model_validate(successful(client.get(
        f"/api/products/{product}/marketplace", headers=HEADERS["BUYER"])).json())
    expert = ExpertMarketplaceResponse.model_validate(successful(client.get(
        f"/api/products/{product}/marketplace", headers=HEADERS["REVIEWER"])).json())
    require(buyer.audience == "BUYER" and expert.audience == "EXPERT" and
            buyer.product_id == expert.product_id == product and buyer.scan_id == expert.scan_id == scan.scan_id,
            "marketplace projection identity mismatch")
    require(buyer.fields == expert.fields, "marketplace tallies are inconsistent")
    require(scan.findings == len(expert.findings), "marketplace scan/findings count differs")
    require(len(buyer.fields) == len({row.field_key for row in buyer.fields}) and
            {row.field_key for row in expert.findings} <= {row.field_key for row in buyer.fields},
            "marketplace tally fields omit/duplicate expert evidence")
    for tally in buyer.fields:
        clusters = {row.cluster for row in expert.findings if row.field_key == tally.field_key}
        require(tally.independent_clusters == len(clusters), "copied seller evidence counted independently")
        value_keys = [json.dumps(row.value, sort_keys=True, ensure_ascii=False) for row in tally.values]
        expected_keys = {json.dumps(row.value, sort_keys=True, ensure_ascii=False) for row in expert.findings
                         if row.field_key == tally.field_key}
        require(len(value_keys) == len(set(value_keys)) and set(value_keys) == expected_keys,
                "marketplace value tallies omit/duplicate expert evidence")
        require(tally.majority is None or json.dumps(tally.majority, sort_keys=True, ensure_ascii=False) in expected_keys,
                "marketplace majority has no supporting value")
        for value in tally.values:
            expected = {row.cluster for row in expert.findings if row.field_key == tally.field_key and row.value == value.value}
            require(value.independent_clusters == len(expected), "value cluster tally differs from expert evidence")
    require(counts() == before, "marketplace GET created work")


def check_web_audit(client: httpx.Client, counts: Callable[[], dict[str, int]], case: str, mode: str) -> None:
    before = counts()
    response = successful(client.get(f"/api/cases/{case}/web-search", headers=HEADERS["REVIEWER"]))
    audit = WebAuditResponse.model_validate(response.json())
    require(audit.case_id == case, "web audit belongs to another case")
    require(all(row.mode == mode.upper() for row in audit.queries), "web audit mode mismatch")
    require(all(result.reason.strip() for row in audit.queries for result in row.results), "web decision lacks a reason")
    require(all(len(row.sha256) == 64 and row.passages and row.captured_at and row.url.startswith("https://")
                for row in audit.snapshots), "web snapshot lacks stored provenance")
    require(client.get(f"/api/cases/{case}/web-search", headers=HEADERS["BUYER"]).status_code == 403,
            "buyer can read expert web audit")
    require(counts() == before, "web audit GET created work")
    # Discovery quality, bounds and confirm-only policy are exercised by the
    # retained offline provider-seam acceptance tests, not by WEB_SEARCH=off.


def check_real_case(client: httpx.Client, database: Path, event: str, product: str, case: str, mode: str) -> None:
    successful(client.post("/api/internal/demo/reset", headers=HEADERS["OPERATOR"]))
    s4_fire(client, event, case, mode)
    passport = s4_passport(client, product)
    require(passport.dataset_origin == "REAL" and {row.field_key for row in passport.fields} == set(PUBLIC_FIELDS), "real passport identity/fields")
    observed = case_state(database, case).fields
    if event == "14-bootstrap-real-hydrating":
        require(all(observed[key].verdict == "CONFLICTING" and observed[key].conflict_locus == "WITHIN_SOURCE"
                    and not observed[key].seller_attributable for key in ("skin_type", "key_ingredients")), "R1 source conflict/attribution differs")
    elif event == "15-bootstrap-real-foaming":
        require(all(observed[key].verdict in {"CONSISTENT", "SINGLE_SOURCE"} for key in ("volume", "skin_type", "key_ingredients"))
                and all(row.verdict != "CONFLICTING" for row in observed.values()), "R2 harmless wording became conflict")
    elif event == "16-bootstrap-real-blemish":
        with closing(sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)) as connection:
            keys = {row[0] for row in connection.execute("SELECT DISTINCT c.field_key FROM claims c JOIN source_versions v "
                "ON v.id=c.source_version_id JOIN sources s ON s.id=v.source_id WHERE s.case_id=? "
                "AND c.field_key IN ('notification_number','responsible_company') AND length(c.raw_value)>0", (case,))}
        require(keys == {"notification_number", "responsible_company"}, "R3 identifiers were not read from sources")
    else:
        alcohol = [row for key, row in observed.items() if key.startswith("claim:free_from:") and "alcohol" in key]
        require(bool(alcohol) and all(row.verdict != "CONFLICTING" and not row.seller_attributable for row in alcohol),
                "R4 alcohol-free audit absent or false conflict")


def run_phase_four(client: httpx.Client, database: Path, fixtures: Path, mode: str) -> list[Check]:
    checks: list[Check] = []
    scenarios: dict[str, tuple[str, str]] = {}
    counts = lambda: table_counts(database)
    for name in ("14-bootstrap-real-hydrating", "15-bootstrap-real-foaming", "16-bootstrap-real-blemish", "17-bootstrap-real-effaclar"):
        path = fixtures / "events" / (name + ".json")
        if not path.exists():
            checks.append(Check(name, "SKIP", "captured real fixture missing; incomplete gate"))
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))["payload"]
        product, case = str(payload["product_id"]), str(payload["case_id"])
        scenarios[name] = product, case
        try:
            check_real_case(client, database, name, product, case, mode)
            checks.append(Check(name, "PASS", "captured REAL case; existing source-grounded expectations"))
        except (CheckFailure, ValidationError, KeyError, ValueError) as error:
            checks.append(Check(name, "FAIL", str(error)))
    demo = json.loads((fixtures / "events/01-bootstrap-demo.json").read_text(encoding="utf-8"))["payload"]
    try:
        check_receipt(client, counts, str(demo["product_id"]), str(demo["case_id"]), mode,
                      lambda receipt_id: stored_receipt(database, receipt_id))
        checks.append(Check("receipt before first revoke", "PASS", "immutable public purchase; two-field diff; duplicate/read-only checks"))
    except (CheckFailure, ValidationError, KeyError, ValueError) as error:
        checks.append(Check("receipt before first revoke", "FAIL", str(error)))
    real = scenarios.get("14-bootstrap-real-hydrating")
    if real is not None:
        product, case = real
        try:
            require(any((fixtures / "marketplace" / product).glob("*.json")), "no marketplace captures")
            check_marketplace(client, counts, product, case, "14-bootstrap-real-hydrating", mode)
            checks.append(Check("marketplace", "PASS", "stored retailer tallies; public passport unchanged; buyer filtering"))
        except (CheckFailure, ValidationError, KeyError, ValueError) as error:
            checks.append(Check("marketplace", "FAIL", str(error)))
        try:
            check_web_audit(client, counts, case, mode)
            checks.append(Check("web audit read", "PASS", "typed role-filtered read only; WEB_SEARCH=off, discovery NOT VERIFIED"))
        except (CheckFailure, ValidationError, KeyError, ValueError) as error:
            checks.append(Check("web audit read", "FAIL", str(error)))
    return checks


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", type=int, choices=(1, 2, 3, 4))
    parser.add_argument("--mode", choices=("fallback", "replay"))
    args = parser.parse_args(argv)
    mode = args.mode if args.mode is not None else os.getenv("LLM_MODE", "fallback")
    if mode not in {"fallback", "replay"}:
        parser.error("select fallback or replay; record/live are not supported by the offline gate")
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
                if args.phase >= 2 and all(check.status == "PASS" for check in checks):
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
                        if args.phase >= 3 and all(check.status == "PASS" for check in checks):
                            missing = [name for name in ("09-catalogue-published", "12-bootstrap-sun-fluid")
                                       if not (config.settings.fixtures_dir / "events" / (name + ".json")).exists()]
                            if missing:
                                checks.append(Check("S3 fixtures", "SKIP", "missing: " + ", ".join(missing)))
                            else:
                                sun_event = json.loads((config.settings.fixtures_dir / "events/12-bootstrap-sun-fluid.json").read_text(encoding="utf-8"))
                                sun_product, sun_case = str(sun_event["payload"]["product_id"]), str(sun_event["payload"]["case_id"])
                                checks.extend(run_phase_three(client, lambda case: case_state(database, case),
                                    lambda: table_counts(database), lambda case: phase_three_probe(database, case),
                                    product_id, case_id, sun_product, sun_case, expected_mode=mode))
            if args.phase == 4 and all(check.status == "PASS" for check in checks):
                with isolated_settings(mode, Path(directory) / "phase4-fresh.db"):
                    with TestClient(create_app()) as client:
                        checks.extend(run_phase_four(client, Path(directory) / "phase4-fresh.db", config.settings.fixtures_dir, mode))
            if network_attempts:
                checks.append(Check("network", "FAIL", "model network call attempted"))
    print("check | status | detail")
    for check in checks:
        print(f"{check.name} | {check.status} | {check.detail}")
    return int(any(check.status != "PASS" for check in checks))


if __name__ == "__main__":
    raise SystemExit(main())
