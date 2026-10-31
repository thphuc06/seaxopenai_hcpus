"""Read-only SQL and role-filtered citation projection shared by S1 routers."""
from contextlib import closing
from threading import Lock
import sqlite3
from typing import cast
from fastapi import HTTPException
from pydantic import JsonValue
from app import config, db
from app.api.contracts import EvidencePassage, RunResponse, RunUsage, ModelCallCounts
from app.models import Citation, PassportField, PassportResponse, Role, RunStatus, PUBLIC_FIELDS

_lock = Lock()
_reads: dict[str, int] = {}


def rows(sql: str, params: tuple[object, ...] = ()) -> list[dict[str, JsonValue]]:
    with closing(db.connect()) as connection:
        return [dict(row) for row in connection.execute(sql, params)]


def one(sql: str, params: tuple[object, ...] = ()) -> dict[str, JsonValue]:
    result = rows(sql, params)
    if not result:
        raise HTTPException(404, "Resource not found")
    return result[0]


def passport_reads(*, increment: bool = False, reset: bool = False) -> int:
    key = str(config.settings.db_path)
    with _lock:
        if reset:
            _reads[key] = 0
        if increment:
            _reads[key] = _reads.get(key, 0) + 1
        return _reads.get(key, 0)


def evidence(citations_json: str, role: Role) -> tuple[list[EvidencePassage], int]:
    with closing(db.connect()) as connection:
        return evidence_snapshot(connection, citations_json, role)


def evidence_snapshot(connection: sqlite3.Connection, citations_json: str, role: Role) -> tuple[list[EvidencePassage], int]:
    citations = [Citation.model_validate(value) for value in cast(list[JsonValue], db.loads(citations_json))]
    visible: list[EvidencePassage] = []
    hidden = 0
    for citation in citations:
        passage = connection.execute("SELECT p.text,s.kind,s.visibility,v.captured_at FROM passages p JOIN source_versions v "
                      "ON v.id=p.source_version_id JOIN sources s ON s.id=v.source_id WHERE p.id=?", (citation.passage_id,)).fetchone()
        if passage is None:
            raise HTTPException(404, "Resource not found")
        if passage["visibility"] == "PRIVATE" and role not in {Role.OPERATOR, Role.REVIEWER, Role.SYSTEM}:
            hidden += 1
            continue
        visible.append(EvidencePassage(**citation.model_dump(),text=passage["text"],source_label="MOCK registry (SYNTHETIC)" if passage["kind"] == "REGISTRY_RECORD" else passage["kind"],
                                      visibility=passage["visibility"],captured_at=passage["captured_at"] or ""))
    return visible, hidden


def passport_snapshot(connection: sqlite3.Connection, product_id: str, role: Role) -> PassportResponse:
    """Project stored public fields within the caller's database snapshot; no counters."""
    product = connection.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    case = connection.execute("SELECT * FROM cases WHERE product_id=?", (product_id,)).fetchone()
    if product is None or case is None:
        raise HTTPException(404, "Resource not found")
    results = connection.execute("SELECT * FROM field_results WHERE case_id=? AND superseded_by IS NULL ORDER BY field_key", (case["id"],)).fetchall()
    latest = connection.execute("SELECT * FROM runs WHERE case_id=? ORDER BY case_revision DESC,created_at DESC LIMIT 1", (case["id"],)).fetchone()
    fields: list[PassportField] = []
    for result in results:
        if result["field_key"] not in PUBLIC_FIELDS:
            continue
        passages, _ = evidence_snapshot(connection, str(result["citations_json"]), role)
        label = "Stale" if result["freshness"] == "STALE" else "Updating" if latest and latest["status"] == "RUNNING" else "Conflict in source" if result["conflict_locus"] == "WITHIN_SOURCE" else {
            "CONSISTENT": "Consistent", "CONFLICTING": "Conflicting", "SINGLE_SOURCE": "Single source",
            "INSUFFICIENT": "Not verified", "UNCERTAIN": "Not verified", "NOT_APPLICABLE": "Not applicable",
        }[str(result["verdict"])]
        fields.append(PassportField(field_key=result["field_key"], label=label, public_text=result["public_text"],
            verdict=result["verdict"], conflict_locus=result["conflict_locus"], freshness=result["freshness"],
            review_state=result["review_state"], checked_at=result["confirmed_at"] or result["created_at"],
            citations=[Citation(**{k: getattr(p, k) for k in Citation.model_fields}) for p in passages]))
    return PassportResponse(product_id=product_id, dataset_origin=product["dataset_origin"],
        last_checked_at=max((str(r["confirmed_at"] or r["created_at"]) for r in results), default=None),
        run_status=latest["status"] if latest else None, fields=fields,
        disclaimer="Describes only the sources checked; it does not establish product origin or suitability.")


def run_usage(row: dict[str, JsonValue]) -> RunUsage:
    usage = db.loads(str(row.get("usage_json") or "{}"))
    calls = usage.get("model_calls", {}) if isinstance(usage, dict) else {}
    used = calls.get("used", 0) if isinstance(calls, dict) else calls or 0
    tokens = one("SELECT COALESCE(SUM(tokens_in),0) AS ti,COALESCE(SUM(tokens_out),0) AS to_ FROM trace_steps WHERE run_id=?", (row["id"],))
    return RunUsage(model_calls=int(used), tokens_in=tokens["ti"], tokens_out=tokens["to_"])


def model_call_counts(*, avoided: int = 0) -> ModelCallCounts:
    """Count case runs and standalone scans without changing the case-run DTO."""
    usage = [(str(row["llm_mode"]).upper(), run_usage(row)) for row in rows("SELECT * FROM runs")]
    return ModelCallCounts(live=sum(item.model_calls for mode, item in usage if mode in {"LIVE", "RECORD"}),
                           replayed=sum(item.model_calls for mode, item in usage if mode == "REPLAY"), avoided=avoided)


def run_response(row: dict[str, JsonValue]) -> RunResponse:
    mode = str(row["llm_mode"]).upper()
    return RunResponse(id=row["id"],case_id=row["case_id"],case_revision=row["case_revision"],
        trigger_event_id=row["trigger_event_id"] or "",status=RunStatus(str(row["status"])),stop_reason=row["stop_reason"],
        llm_mode="LIVE" if mode == "RECORD" else mode,started_at=row["started_at"],finished_at=row["finished_at"],
        usage=run_usage(row))
