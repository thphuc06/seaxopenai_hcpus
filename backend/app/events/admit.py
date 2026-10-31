"""Transactional admission and revision scheduling; no model calls."""
from collections.abc import Mapping
from dataclasses import dataclass
import sqlite3
from uuid import uuid4
from app import config, db
from app.models import AdmitResult, EventEnvelope, EventOutcome, EventType, Role
from app.pipeline.policy import stale_freshness


@dataclass(frozen=True)
class AdmissionRules:
    producers: Mapping[str, frozenset[EventType]]
    non_material: frozenset[str]


# P4 owns the single closed-set protocol configuration; tests may inject rules.
DEFAULT_RULES = AdmissionRules(config.PRODUCER_EVENT_TYPES, config.NON_MATERIAL_FIELDS)


def _case(connection: sqlite3.Connection, event: EventEnvelope) -> sqlite3.Row | None:
    if event.resource.kind == "CASE":
        row = connection.execute("SELECT * FROM cases WHERE id=?", (event.resource.id,)).fetchone()
    elif event.resource.kind == "LISTING":
        row = connection.execute("SELECT c.* FROM cases c JOIN products p ON p.id=c.product_id WHERE p.listing_id=?", (event.resource.id,)).fetchone()
    else:
        row = connection.execute("SELECT c.* FROM cases c JOIN sources s ON s.case_id=c.id WHERE s.id=?", (event.resource.id,)).fetchone()
    if row and (event.payload.get("case_id", row["id"]) != row["id"]
                or event.payload.get("product_id", row["product_id"]) != row["product_id"]):
        return None
    return row


def admit(event: EventEnvelope, *, role: Role, actor_id: str, rules: AdmissionRules = DEFAULT_RULES) -> AdmitResult:
    """Identity supplied by server dependency, never by event arguments."""
    with db.transaction() as connection:
        allowed = role in {Role.OPERATOR, Role.SYSTEM} or role == Role.SELLER and event.type == EventType.EVIDENCE_ADDED
        accepted = bool(actor_id.strip()) and allowed and event.type in rules.producers.get(event.producer, frozenset())
        existing = connection.execute("SELECT id FROM events WHERE idempotency_key=?", (event.idempotency_key,)).fetchone()
        if accepted and existing:
            return AdmitResult(event_id=event.event_id, outcome=EventOutcome.DUPLICATE,
                               reason="Idempotency key already recorded", job_id=None, stale_fields=[])
        case = _case(connection, event) if accepted else None
        outcome = EventOutcome.REJECTED
        reason = "Producer or role not allowed" if not accepted else "Resource does not match a case"
        if case:
            outcome, reason = EventOutcome.ADMITTED, "Material event admitted"
            if event.type == EventType.LISTING_CHANGED and set(event.changed_fields) <= rules.non_material:
                outcome, reason = EventOutcome.NOOP, "Only non-material fields changed"
        event_id = "event_" + uuid4().hex
        connection.execute("INSERT INTO events(id,idempotency_key,type,producer,resource_id,resource_version,payload_json,received_at,outcome,reason,event_id) "
                           "VALUES(?,?,?,?,?,?,?,?,?,?,?)", (event_id, None if existing else event.idempotency_key,
                           event.type,event.producer,event.resource.id,str(event.resource.version),event.model_dump_json(),
                           db.now_iso(),outcome,reason,event.event_id))
        stale: list[str] = []
        job_id = None
        if outcome == EventOutcome.ADMITTED and case:
            if event.type in {EventType.LISTING_CHANGED, EventType.SOURCE_CHANGED, EventType.SOURCE_REVOKED}:
                changed_sources = {row[0] for row in connection.execute(
                    "SELECT id FROM sources WHERE case_id=? AND kind='LISTING'", (case["id"],))} if event.resource.kind == "LISTING" else {event.resource.id}
                for result in connection.execute("SELECT id,field_key,depends_on_json FROM field_results WHERE case_id=? AND superseded_by IS NULL", (case["id"],)).fetchall():
                    dependencies = db.loads(result["depends_on_json"])
                    changed = isinstance(dependencies, list) and any(
                        isinstance(d, dict) and d.get("source_id") in changed_sources for d in dependencies)
                    if changed:
                        connection.execute("UPDATE field_results SET freshness=?,stale_at=?,stale_reason=? WHERE id=?",
                                           (stale_freshness(),db.now_iso(),event.type,result["id"]))
                        stale.append(result["field_key"])
            revision = case["revision"] + 1
            connection.execute("UPDATE cases SET revision=? WHERE id=?", (revision,case["id"]))
            queued = connection.execute("SELECT id FROM jobs WHERE case_id=? AND status='QUEUED'", (case["id"],)).fetchone()
            job_id = queued[0] if queued else "job_" + uuid4().hex
            if queued:
                connection.execute("UPDATE jobs SET target_revision=?,trigger_event_id=? WHERE id=?", (revision,event_id,job_id))
            else:
                connection.execute("INSERT INTO jobs(id,case_id,target_revision,trigger_event_id,status,created_at) VALUES(?,?,?,?,'QUEUED',?)",
                                   (job_id,case["id"],revision,event_id,db.now_iso()))
        connection.execute("UPDATE events SET payload_json=? WHERE id=?", (db.dumps({"event": event.model_dump(mode="json"),
                           "stale_fields": sorted(set(stale)), "job_id": job_id}),event_id))
        return AdmitResult(event_id=event.event_id,outcome=outcome,reason=reason,job_id=job_id,stale_fields=sorted(set(stale)))
