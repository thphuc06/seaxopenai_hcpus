"""The sole transactional publication boundary for runs and reviewer inputs."""
import re
import sqlite3
import unicodedata
from uuid import uuid4
from pydantic import JsonValue
from app import db
from app.models import FieldDecision, Verdict
from app.pipeline import policy
from app.trace import TraceWriter

# Canonical expression from docs06 / test_guards; this literal defines a guard, not product text.
FORBIDDEN = re.compile(r"\b(?:genuine|authentic|fake|counterfeit|safe|certified|verified product|chính hãng|hàng giả|an toàn)\b", re.IGNORECASE)


def quote_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def _validate(connection: sqlite3.Connection, decision: FieldDecision, run_id: str, case_id: str) -> str | None:
    run = connection.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    case = connection.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
    if not run or not case or run["case_id"] != case_id:
        return "CASE_MISMATCH"
    if run["case_revision"] != case["revision"]:
        return "SUPERSEDED_RUN"
    if FORBIDDEN.search(decision.public_text):
        return "FORBIDDEN_WORDING"
    if decision.verdict != Verdict.INSUFFICIENT and not decision.citations:
        return "NO_CITATION"
    for citation in decision.citations:
        passage = connection.execute(
            "SELECT p.*, v.version, v.is_current, s.kind, s.case_id, s.status FROM passages p "
            "JOIN source_versions v ON v.id=p.source_version_id JOIN sources s ON s.id=v.source_id WHERE p.id=?",
            (citation.passage_id,),
        ).fetchone()
        if not passage or passage["case_id"] != case_id:
            return "INVALID_LOCATOR"
        if passage["status"] != "ACTIVE" or not passage["is_current"]:
            return "INACTIVE_SOURCE"
        if (passage["version"] != citation.source_version or passage["kind"] != citation.source_kind
                or passage["locator"] != citation.locator or not quote_text(citation.excerpt)
                or quote_text(citation.excerpt) not in quote_text(passage["text"])):
            return "INVALID_LOCATOR"
    for dependency in decision.depends_on:
        source = connection.execute("SELECT s.case_id FROM sources s JOIN source_versions v ON v.source_id=s.id "
                                    "WHERE s.id=? AND v.id=?", (dependency.source_id, dependency.source_version_id)).fetchone()
        if not source or source[0] != case_id:
            return "INVALID_DEPENDENCY"
    return None


def _record_result(connection: sqlite3.Connection, decision: FieldDecision, run_id: str,
                   case_id: str, now: str) -> tuple[str, bool]:
    value = decision.model_dump(mode="json")
    persisted: dict[str, JsonValue] = {name: value[name] for name in (
        "verdict", "conflict_locus", "scope_match", "review_state", "evidence_level", "public_text")}
    persisted["seller_attributable"] = int(decision.seller_attributable)
    persisted["policy_version"] = policy.POLICY_VERSION
    for name in ("citations", "depends_on", "notes", "explain"):
        persisted[name + "_json"] = db.dumps(value[name])
    previous = connection.execute("SELECT * FROM field_results WHERE case_id=? AND field_key=? AND superseded_by IS NULL",
                                  (case_id,decision.field_key)).fetchone()
    if previous and all(previous[key] == val for key,val in persisted.items()):
        connection.execute("UPDATE field_results SET confirmed_run_id=?,confirmed_at=?,freshness=?,stale_at=NULL,stale_reason=NULL WHERE id=?",
                           (run_id,now,policy.current_freshness(),previous["id"]))
        return previous["id"], True
    revision = connection.execute("SELECT case_revision FROM runs WHERE id=?", (run_id,)).fetchone()[0]
    version = connection.execute("SELECT COALESCE(MAX(result_version),0)+1 FROM field_results WHERE case_id=? AND field_key=?",
                                 (case_id,decision.field_key)).fetchone()[0]
    result_id = "result_" + uuid4().hex
    record: dict[str, JsonValue] = dict(persisted, id=result_id,case_id=case_id,field_key=decision.field_key,
        result_version=version,case_revision=revision,freshness=policy.current_freshness(),run_id=run_id,created_at=now)
    columns = ",".join(record)
    placeholders = ",".join("?" for _ in record)
    # All column names are the closed set constructed above, never caller input.
    connection.execute(f"INSERT INTO field_results({columns}) VALUES({placeholders})", tuple(record.values()))
    if previous:
        connection.execute("UPDATE field_results SET superseded_by=? WHERE id=?", (result_id,previous["id"]))
    return result_id, False


def _record_gap(connection: sqlite3.Connection, decision: FieldDecision, run_id: str, case_id: str, now: str) -> None:
    open_gaps = connection.execute("SELECT * FROM gaps WHERE case_id=? AND field_key=? AND status='OPEN'",
                                   (case_id,decision.field_key)).fetchall()
    for previous in open_gaps:
        if decision.gap and previous["missing_kind"] == decision.gap.missing_kind:
            return
        connection.execute("UPDATE gaps SET status='CLOSED' WHERE id=?", (previous["id"],))
        connection.execute("UPDATE evidence_requests SET status='CLOSED' WHERE gap_id=?", (previous["id"],))
    if decision.gap:
        gap, gap_id = decision.gap, "gap_" + uuid4().hex
        connection.execute("INSERT INTO gaps(id,case_id,field_key,missing_kind,needed_doc,known_ids_json,tried_json,status,run_id,created_at) "
                           "VALUES(?,?,?,?,?,?,?,'OPEN',?,?)",
                           (gap_id,case_id,decision.field_key,gap.missing_kind,gap.needed_doc,db.dumps(gap.known_ids),"[]",run_id,now))
        connection.execute("INSERT INTO evidence_requests(id,case_id,field_key,gap_id,reason,requested_from,status,created_at) "
                           "VALUES(?,?,?,?,?,'SELLER','OPEN',?)",
                           ("request_"+uuid4().hex,case_id,decision.field_key,gap_id,gap.reason,now))


def gate(decision: FieldDecision, run: dict[str, JsonValue], case: dict[str, JsonValue]) -> bool:
    """Validate all evidence and the stored current revision under the writer lock."""
    run_id, case_id = str(run["id"]), str(case["id"])
    now = db.now_iso()
    with db.transaction() as connection:
        reason = _validate(connection, decision, run_id, case_id)
        # Delayed public gate callers may have stored a minimal run row.
        connection.execute("UPDATE runs SET created_at=COALESCE(created_at,?) WHERE id=?", (now, run_id))
        if reason is None:
            result_id, confirmed = _record_result(connection,decision,run_id,case_id,now)
            _record_gap(connection,decision,run_id,case_id,now)
    trace = TraceWriter(run_id)
    if reason:
        trace.step("publish:blocked", detail={"reason": reason, "field_key": decision.field_key})
        return False
    trace.step("publish", output_refs=[result_id], detail={"field_key": decision.field_key,"confirmed": confirmed})
    return True
