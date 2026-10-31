"""The sole transactional publication boundary for runs and reviewer inputs."""
import re
import sqlite3
import unicodedata
from uuid import uuid4
from pydantic import JsonValue
from app import chain, db
from app.models import FieldDecision, Verdict, DependsOn
from app.pipeline import policy
from app.trace import TraceWriter


class ReviewError(ValueError):
    def __init__(self, status: int, reason: str):
        super().__init__(reason)
        self.status = status


def _stored_decision(connection: sqlite3.Connection, row: sqlite3.Row) -> FieldDecision:
    value = {name: row[name] for name in ("field_key","verdict","conflict_locus","scope_match","review_state","evidence_level","seller_attributable","public_text")}
    for name in ("citations","depends_on","notes","explain"):
        value[name] = db.loads(row[name+"_json"])
    gap = connection.execute("SELECT * FROM gaps WHERE case_id=? AND field_key=? AND status='OPEN'",(row["case_id"],row["field_key"])).fetchone()
    value.update(gap={"field_key":row["field_key"],"missing_kind":gap["missing_kind"],"needed_doc":gap["needed_doc"],"known_ids":db.loads(gap["known_ids_json"]),"reason":"Further evidence is required"} if gap else None,needs_scope_resolution=False)
    return FieldDecision.model_validate(value)


def confirm_unchanged(run_id: str, case_id: str, excluded_fields: list[str]) -> list[FieldDecision]:
    """Validate retained CURRENT findings and bind their review tasks to this revision."""
    retained: list[FieldDecision] = []
    confirmed_ids: list[tuple[str,bool]] = []
    blocked: list[tuple[str,str]] = []
    with db.transaction() as connection:
        run = connection.execute("SELECT case_revision FROM runs WHERE id=? AND case_id=?",(run_id,case_id)).fetchone()
        if not run:
            return retained
        for row in connection.execute("SELECT * FROM field_results WHERE case_id=? AND superseded_by IS NULL AND freshness='CURRENT'",(case_id,)).fetchall():
            if row["field_key"] in excluded_fields:
                continue
            previous = _stored_decision(connection,row)
            finding = policy.reconfirm_decision(previous,row["case_revision"],run["case_revision"])
            reason = _validate(connection,finding,run_id,case_id)
            if reason:
                blocked.append((row["field_key"],reason))
                continue
            result_id = row["id"]
            unchanged = finding == previous
            if unchanged:
                connection.execute("UPDATE field_results SET confirmed_run_id=?,confirmed_at=? WHERE id=?",(run_id,db.now_iso(),result_id))
            else:
                result_id,_ = _record_result(connection,finding,run_id,case_id,db.now_iso())
            _record_review_task(connection,finding,case_id,result_id)
            retained.append(finding)
            confirmed_ids.append((result_id,unchanged))
    for identity,unchanged in confirmed_ids:
        TraceWriter(run_id).step("publish",output_refs=[identity],detail={"confirmed":unchanged,"unchanged":unchanged})
    for field,reason in blocked:
        TraceWriter(run_id).step("publish:blocked",detail={"field_key":field,"reason":reason})
    return retained


def review(case_id: str, result_id: str, revision: int, decision: str, reason: str,
           override: dict[str, JsonValue] | None, reviewer_id: str) -> str:
    """One writer transaction binds review and publication to the exact revision."""
    with db.transaction() as connection:
        case = connection.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
        old = connection.execute("SELECT * FROM field_results WHERE id=? AND case_id=?", (result_id,case_id)).fetchone()
        if not case or not old:
            raise ReviewError(404, "Case or result not found")
        confirmation = connection.execute("SELECT case_revision FROM runs WHERE id=?",(old["confirmed_run_id"],)).fetchone()
        bound_revision = confirmation[0] if confirmation else old["case_revision"]
        if case["revision"] != revision or bound_revision != revision or old["superseded_by"]:
            raise ReviewError(409, "Review revision is no longer current")
        try:
            finding = policy.reviewed_decision(_stored_decision(connection,old),decision,override)
        except ValueError as error:
            raise ReviewError(422, str(error)) from error
        now, run_id, review_id = db.now_iso(), "review_run_"+uuid4().hex, "review_"+uuid4().hex
        connection.execute("INSERT INTO runs(id,case_id,case_revision,status,llm_mode,created_at,started_at,finished_at,policy_version,model,prompt_version,usage_json) VALUES(?,?,?,'COMPLETED','FALLBACK',?,?,?,?,'HUMAN','review-v1','{}')", (run_id,case_id,revision,now,now,now,policy.POLICY_VERSION))
        blocked = _validate(connection,finding,run_id,case_id)
        if blocked:
            raise ReviewError(422, blocked)
        finding.depends_on = [DependsOn(source_id=row["source_id"],source_version_id=row["source_version_id"]) for row in connection.execute(
            "SELECT DISTINCT v.source_id,p.source_version_id FROM passages p JOIN source_versions v ON v.id=p.source_version_id WHERE p.id IN ("+
            ",".join("?" for _ in finding.citations)+")",tuple(c.passage_id for c in finding.citations))] if finding.citations else []
        published, _ = _record_result(connection,finding,run_id,case_id,now)
        _record_gap(connection,finding,run_id,case_id,now)
        connection.execute("UPDATE field_results SET reviewed_by=? WHERE id=?", (reviewer_id,published))
        connection.execute("INSERT INTO reviews VALUES(?,?,?,?,?,?,?,?,?)",
                           (review_id,case_id,result_id,revision,reviewer_id,decision,reason,db.dumps(override),now))
        connection.execute("UPDATE review_tasks SET status='CLOSED' WHERE result_id=?", (result_id,))
    trace = TraceWriter(run_id)
    trace.step("pin_revision",actor="human",detail={"case_revision":revision})
    trace.step("publish",actor="human",output_refs=[published],detail={"review_id":review_id})
    trace.step("run:stop",actor="human",detail={"status":"COMPLETED","model_calls":0})
    return review_id

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
    chain.append(connection, result_id)
    if previous:
        connection.execute("UPDATE field_results SET superseded_by=? WHERE id=?", (result_id,previous["id"]))
    return result_id, False


def _record_gap(connection: sqlite3.Connection, decision: FieldDecision, run_id: str, case_id: str, now: str) -> None:
    open_gaps = connection.execute("SELECT * FROM gaps WHERE case_id=? AND field_key=? AND status='OPEN'",
                                   (case_id,decision.field_key)).fetchall()
    for previous in open_gaps:
        if decision.gap:
            connection.execute("UPDATE gaps SET missing_kind=?,needed_doc=? WHERE id=?",(decision.gap.missing_kind,decision.gap.needed_doc,previous["id"]))
            connection.execute("UPDATE evidence_requests SET reason=? WHERE gap_id=? AND status='OPEN'",(decision.gap.reason,previous["id"]))
            return
        connection.execute("UPDATE gaps SET status='CLOSED' WHERE id=?", (previous["id"],))
        connection.execute("UPDATE evidence_requests SET status='FULFILLED' WHERE gap_id=?", (previous["id"],))
    if decision.gap:
        gap, gap_id = decision.gap, "gap_" + uuid4().hex
        connection.execute("INSERT INTO gaps(id,case_id,field_key,missing_kind,needed_doc,known_ids_json,tried_json,status,run_id,created_at) "
                           "VALUES(?,?,?,?,?,?,?,'OPEN',?,?)",
                           (gap_id,case_id,decision.field_key,gap.missing_kind,gap.needed_doc,db.dumps(gap.known_ids),"[]",run_id,now))
        connection.execute("INSERT INTO evidence_requests(id,case_id,field_key,gap_id,reason,requested_from,status,created_at) "
                           "VALUES(?,?,?,?,?,'SELLER','OPEN',?)",
                           ("request_"+uuid4().hex,case_id,decision.field_key,gap_id,gap.reason,now))


def _record_review_task(connection: sqlite3.Connection, decision: FieldDecision, case_id: str, result_id: str) -> None:
    if decision.review_state == "NEEDS_REVIEW" and not connection.execute(
        "SELECT 1 FROM review_tasks WHERE result_id=? AND status='OPEN'", (result_id,)).fetchone():
        connection.execute("INSERT INTO review_tasks VALUES(?,?,?,?,?,'OPEN')",
                           ("task_"+uuid4().hex,case_id,decision.field_key,result_id,"POLICY_REVIEW"))


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
            _record_review_task(connection,decision,case_id,result_id)
    trace = TraceWriter(run_id)
    if reason:
        trace.step("publish:blocked", detail={"reason": reason, "field_key": decision.field_key})
        return False
    trace.step("publish", output_refs=[result_id], detail={"field_key": decision.field_key,"confirmed": confirmed})
    return True
