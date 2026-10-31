"""Code-led, budgeted MOCK registry evidence discovery."""
from dataclasses import dataclass
from hashlib import sha256
from app import db, store
from app.connectors import registry
from app.budget import BudgetExceeded
from app.context import RunContext
from app.models import FieldDecision, ScopeMatch, SourceKind, SourceStatus
from app.pipeline import normalize, publish
from app.pipeline.scope import infer_scope
from app.pipeline.policy import SourceObs


@dataclass
class GapOutcome:
    new_sv_ids: list[str]
    stops: list[str]


def close_gaps(ctx: RunContext, decisions: list[FieldDecision], observations: list[SourceObs]) -> GapOutcome:
    if not any(d.gap and d.gap.missing_kind == "NOTIFICATION_DOC" for d in decisions):
        return GapOutcome([], [])
    ctx.budget.take_tool("gap:join_key")
    keys = sorted({str(o.normalized.get("value", "")) for o in observations
        if o.field_key == "notification_number" and o.source_kind in {SourceKind.LISTING, SourceKind.PACKAGING_IMAGE}
        and o.status == SourceStatus.ACTIVE and o.scope_match == ScopeMatch.MATCH and o.quote and o.normalized.get("value")
        and any(publish.quote_text(o.quote) in publish.quote_text(str(p["text"])) for p in store.passages(o.source_version_id) if p["id"] == o.passage_id)})
    ctx.trace.step("gap:hop1:join_key", detail={"keys": len(keys), "origin": "SYNTHETIC", "registry": "MOCK"})
    result = GapOutcome([], [])
    if not keys:
        result.stops.append("NO_JOIN_KEY")
    try:
        registry_revision = registry.revision() if keys else ""
    except OSError as error:
        ctx.trace.step("gap:stop", error=type(error).__name__, detail={"stop_reason":"REGISTRY_ERROR","registry":"MOCK"})
        return GapOutcome([], ["REGISTRY_ERROR"])
    for number in keys[:2]:
        source_id = "registry_" + sha256((ctx.case_id+":"+number).encode("utf-8")).hexdigest()
        with db.transaction() as connection:
            attempts = [db.loads(row[0]) for row in connection.execute(
                "SELECT t.detail FROM trace_steps t JOIN runs r ON r.id=t.run_id WHERE r.case_id=? AND t.step='gap:hop2:registry'", (ctx.case_id,))]
            tried = [attempt.get("number") for attempt in attempts if attempt.get("found") is False and attempt.get("registry_revision") == registry_revision]
        if number in tried or any(s["id"] == source_id for s in store.current_sources(ctx.case_id)):
            result.stops.append("ALREADY_CHECKED")
            continue
        try:
            ctx.budget.take_tool("gap:registry_lookup")
        except BudgetExceeded as error:
            result.stops.append(error.reason)
            break
        try:
            record = registry.lookup(number)
        except (OSError, ValueError, KeyError, TypeError) as error:
            ctx.trace.step("gap:hop2:registry", error=type(error).__name__, detail={"stop_reason":"REGISTRY_ERROR","registry":"MOCK","origin":"SYNTHETIC"})
            result.stops.append("REGISTRY_ERROR")
            break
        ctx.trace.step("gap:hop2:registry", detail={"number":number,"registry_revision":registry_revision,"found": record is not None, "registry": "MOCK", "origin": "SYNTHETIC"})
        if record is None:
            result.stops.append("NOT_FOUND")
            continue
        snapshot: dict[str, db.JSON] = {"source_id": source_id, "product_id": ctx.product["id"], "kind": "REGISTRY_RECORD", "version": 1,
            "visibility": "PUBLIC", "family": "mock-registry", "uri": "mock://registry/"+source_id, "owner": "MOCK registry",
            "captured_at": record.issued, "scope": {"product":ctx.product["id"], "registry_number":number,"registry_holder":record.holder},
            "passages": [{"locator":"registry:number","section":"notification_number","text":"MOCK registry notification number: "+number},
                         {"locator":"registry:holder","section":"responsible_company","text":"MOCK registry responsible company: "+record.holder}]}
        try:
            ctx.budget.check_active()
        except BudgetExceeded as error:
            result.stops.append(error.reason)
            break
        ref = store.add_source_version(snapshot, case_id=ctx.case_id, origin="SYNTHETIC")
        if record.status == "REVOKED":
            with db.transaction() as connection:
                connection.execute("UPDATE sources SET status='REVOKED' WHERE id=?", (source_id,))
            result.stops.append("REVOKED_IN_REGISTRY")
        result.new_sv_ids.append(ref.id)
    for stop in result.stops:
        ctx.trace.step("gap:stop", detail={"stop_reason":stop,"registry":"MOCK","origin":"SYNTHETIC"})
    return result


def registry_observations(source: dict[str, db.JSON], ctx: RunContext) -> list[SourceObs]:
    observations: list[SourceObs] = []
    passages = store.passages(str(source["source_version_id"]))
    scoped_source = dict(source, passages=passages)
    inferred = infer_scope(scoped_source, ctx.product)
    for passage in passages:
        field = str(passage["section"])
        if field not in {"notification_number", "responsible_company"}:
            continue
        prefix = "MOCK registry notification number: " if field == "notification_number" else "MOCK registry responsible company: "
        text = str(passage["text"])
        if not text.startswith(prefix) or not text[len(prefix):].strip():
            continue
        raw = text[len(prefix):].strip()
        observations.append(SourceObs(source_id=str(source["id"]), source_version_id=str(source["source_version_id"]), source_version=int(str(source["version"])),
            source_kind=SourceKind.REGISTRY_RECORD, family=str(source["family"]), status=SourceStatus(str(source["status"])), visibility=source["visibility"],
            scope_match=inferred.for_passage(str(passage["id"])).scope_match, case_id=ctx.case_id, tenant_id=ctx.tenant_id, field_key=field,
            passage_id=str(passage["id"]), locator=str(passage["locator"]), quote=str(passage["text"]), normalized=normalize.normalize(field, str(raw)) or {}))
    return observations
