"""Read-only SQL and role-filtered citation projection shared by S1 routers."""
from contextlib import closing
from threading import Lock
from typing import cast
from fastapi import HTTPException
from pydantic import JsonValue
from app import config, db
from app.api.contracts import EvidencePassage, RunResponse, RunUsage
from app.models import Citation, Role, RunStatus

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
    citations = [Citation.model_validate(value) for value in cast(list[JsonValue], db.loads(citations_json))]
    visible: list[EvidencePassage] = []
    hidden = 0
    for citation in citations:
        passage = one("SELECT p.text,s.kind,s.visibility,v.captured_at FROM passages p JOIN source_versions v "
                      "ON v.id=p.source_version_id JOIN sources s ON s.id=v.source_id WHERE p.id=?", (citation.passage_id,))
        if passage["visibility"] == "PRIVATE" and role not in {Role.OPERATOR, Role.REVIEWER, Role.SYSTEM}:
            hidden += 1
            continue
        visible.append(EvidencePassage(**citation.model_dump(),text=passage["text"],source_label="MOCK registry (SYNTHETIC)" if passage["kind"] == "REGISTRY_RECORD" else passage["kind"],
                                      visibility=passage["visibility"],captured_at=passage["captured_at"] or ""))
    return visible, hidden


def run_response(row: dict[str, JsonValue]) -> RunResponse:
    usage = db.loads(str(row.get("usage_json") or "{}"))
    calls = usage.get("model_calls", {}) if isinstance(usage, dict) else {}
    used = calls.get("used", 0) if isinstance(calls, dict) else calls or 0
    tokens = one("SELECT COALESCE(SUM(tokens_in),0) AS ti,COALESCE(SUM(tokens_out),0) AS to_ FROM trace_steps WHERE run_id=?", (row["id"],))
    mode = str(row["llm_mode"]).upper()
    return RunResponse(id=row["id"],case_id=row["case_id"],case_revision=row["case_revision"],
        trigger_event_id=row["trigger_event_id"] or "",status=RunStatus(str(row["status"])),stop_reason=row["stop_reason"],
        llm_mode="LIVE" if mode == "RECORD" else mode,started_at=row["started_at"],finished_at=row["finished_at"],
        usage=RunUsage(model_calls=int(used),tokens_in=tokens["ti"],tokens_out=tokens["to_"]))
