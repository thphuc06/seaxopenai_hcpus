"""Pinned-revision orchestration. Extraction is a replaceable P2 seam."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast, Literal
from uuid import uuid4
import sqlite3
from pydantic import JsonValue

from app import config, db, store
from app.budget import Budget, BudgetExceeded
from app.context import RunContext
from app.llm.client import LLMError
from app.models import PUBLIC_FIELDS, FieldDecision, Readability, ReviewState, ScopeMatch, SourceKind, SourceStatus
from app.pipeline import claims_audit, compare, extract, normalize, policy, publish
from app.pipeline.scope import infer_scope, volume_claim_scope
from app.trace import TraceWriter

Extractor = Callable[[str, RunContext], extract.Extraction]


@dataclass(frozen=True)
class Job:
    id: str
    case_id: str
    target_revision: int
    trigger_event_id: str


def _observations(source: dict[str, JsonValue], product: dict[str, JsonValue], ctx: RunContext,
                  extractor: Extractor) -> list[policy.SourceObs]:
    sv_id = str(source["source_version_id"])
    source = dict(source)
    source["passages"] = store.passages(sv_id)
    with db.transaction() as connection:
        source["passage_scopes"] = [dict(row) for row in connection.execute("SELECT * FROM passage_scopes WHERE source_version_id=?",(sv_id,))]
    inferred = infer_scope(source,product)
    scope, reason = inferred.scope_match, inferred.reason
    ctx.trace.step("scope_check", input_refs=[sv_id], detail={"scope_match": scope.value, "reason": reason})
    passages = {str(p["id"]): p for p in store.passages(sv_id)}
    common = dict(source_id=str(source["id"]), source_version_id=sv_id, source_version=int(str(source["version"])),
                  source_kind=SourceKind(str(source["kind"])), family=str(source["family"] or source["id"]),
                  status=SourceStatus(str(source["status"])), visibility=cast(Literal["PUBLIC", "PRIVATE"], source["visibility"]),
                  scope_match=scope, case_id=ctx.case_id, tenant_id=ctx.tenant_id)
    # Empty observations retain dependency information even when extraction yields no claims.
    observations = [policy.SourceObs(**common,field_key="",passage_id="",locator="",quote="",normalized={})]
    if scope == ScopeMatch.MISMATCH or source["status"] != SourceStatus.ACTIVE:
        return observations
    if ctx.budget.remaining_s() <= 0:
        raise BudgetExceeded("RUN_DEADLINE")
    with ctx.trace.timed("extract", "code" if ctx.mode == "fallback" else "llm"):
        result = extractor(sv_id, ctx)
    # Extraction can remove promotional quantities before observations are built.
    # Retain their exclusion evidence through the same scope classifier.
    for passage_id, passage in passages.items():
        for value in normalize.volumes_in(str(passage["text"])):
            quantity_scope, quantity_reason = volume_claim_scope(str(passage["text"]), value)
            retained = any(claim.passage_id == passage_id and claim.field_key == "volume"
                           and compare.same_volume(claim.normalized, value) for claim in result.claims)
            if quantity_scope != ScopeMatch.MATCH and not retained:
                ctx.trace.step("scope_check", input_refs=[passage_id], detail={
                    "field_key": "volume", "scope_match": quantity_scope.value,
                    "reason": quantity_reason, "excluded_before_scope": True})
    for claim in result.claims:
        passage = passages.get(claim.passage_id)
        if claim.source_version_id != sv_id or not passage:
            ctx.trace.step("extract", detail={"reason": "INVALID_LOCATOR"})
            continue
        quote = claim.quote or ""
        if claim.readability != Readability.UNREADABLE and (
            not publish.quote_text(quote) or publish.quote_text(quote) not in publish.quote_text(str(passage["text"]))
        ):
            ctx.trace.step("extract", detail={"reason": "INVALID_LOCATOR"})
            continue
        claim_scope = inferred.for_passage(claim.passage_id).scope_match
        if claim.field_key == "volume" and claim.readability != Readability.UNREADABLE:
            quantity_scope, quantity_reason = volume_claim_scope(str(passage["text"]),claim.normalized)
            if quantity_scope != ScopeMatch.MATCH and claim_scope != ScopeMatch.MISMATCH:
                claim_scope = quantity_scope
                ctx.trace.step("scope_check",input_refs=[claim.passage_id],detail={
                    "field_key":"volume","scope_match":claim_scope.value,"reason":quantity_reason})
        placed = dict(common,scope_match=claim_scope)
        observations.append(policy.SourceObs(**placed,field_key=claim.field_key,passage_id=claim.passage_id,
            locator=str(passage["locator"]),quote=quote,normalized=claim.normalized,
            readability=claim.readability,mapped_by=claim.mapped_by))
    return observations


def run(job: Job, *, extractor: Extractor | None = None) -> str:
    """P2's extract_source_version is the default; tests can inject an external extractor."""
    run_id, now = "run_" + uuid4().hex, db.now_iso()
    budget = Budget.from_settings()
    mode = "replay" if config.settings.replay_freeze and config.settings.llm_mode != "fallback" else config.settings.llm_mode
    with db.transaction() as connection:
        case_row = connection.execute("SELECT * FROM cases WHERE id=?", (job.case_id,)).fetchone()
        if not case_row:
            raise ValueError("Case does not exist")
        case = dict(case_row)
        product_row = connection.execute("SELECT * FROM products WHERE id=?", (case["product_id"],)).fetchone()
        product: dict[str, JsonValue] = dict(product_row)
        product.update(case_id=case["id"], tenant_id=case["tenant_id"], web=db.loads(product.get("web_json") or "{}"))
        connection.execute("INSERT INTO runs(id,case_id,case_revision,trigger_event_id,status,policy_version,llm_mode,budget_json,started_at,created_at,model,prompt_version) "
                           "VALUES(?,?,?,?,'RUNNING',?,?,?,?,?,?,?)", (run_id,job.case_id,job.target_revision,job.trigger_event_id,
                           policy.POLICY_VERSION,"LIVE" if mode == "record" else mode.upper(),db.dumps(budget.usage()),now,now,
                           "FALLBACK" if mode == "fallback" else config.settings.model_extract,extract.PROMPT_VERSION))
        connection.execute("UPDATE jobs SET run_id=? WHERE id=?", (run_id,job.id))
        connection.execute("UPDATE events SET run_id=? WHERE id=?", (run_id,job.trigger_event_id))
        stale_fields = [row[0] for row in connection.execute("SELECT field_key FROM field_results WHERE case_id=? "
                        "AND superseded_by IS NULL AND freshness='STALE' ORDER BY field_key", (job.case_id,))]
    trace = TraceWriter(run_id)
    ctx = RunContext(run_id,job.case_id,str(case["tenant_id"]),job.target_revision,product,mode,budget,trace)
    with db.transaction() as connection:
        event = connection.execute("SELECT payload_json,received_at,type FROM events WHERE id=?", (job.trigger_event_id,)).fetchone()
    if stale_fields:
        trace.step("stale:mark",detail={"event_id":job.trigger_event_id,"fields": stale_fields,"model_calls":0,
                                       "admitted_at": event["received_at"] if event else now})
    trace.step("pin_revision",detail={"case_revision": job.target_revision,"mode": "LIVE" if mode == "record" else mode.upper(),"policy_version": policy.POLICY_VERSION})
    status, stop_reason, error = "FAILED", None, None
    observations: list[policy.SourceObs] = []
    decisions: list[FieldDecision] = []
    published = 0
    try:
        if case["revision"] != job.target_revision:
            stop_reason = "SUPERSEDED_RUN"
            status = "CANCELLED"
        else:
            for source in store.current_sources(job.case_id):
                try:
                    observations.extend(_observations(source, product, ctx, extractor or extract.extract_source_version))
                    if budget.stop_reason:
                        # Optional retries may retain valid claims after exhausting the budget.
                        raise BudgetExceeded(budget.stop_reason)
                except BudgetExceeded as failure:
                    stop_reason = failure.reason
                    trace.step("run:stop", detail={"stop_reason": stop_reason})
                    break
                except LLMError as failure:
                    stop_reason, error = failure.code, type(failure).__name__
                    trace.step("run:stop",detail={"stop_reason": stop_reason},error=error)
                    break
            product["passage_texts"] = {str(p["id"]):str(p["text"]) for version in {o.source_version_id for o in observations} for p in store.passages(version)}
            no_claims_model_error = error is not None and not any(o.normalized for o in observations)
            for field in PUBLIC_FIELDS:
                if event and event["type"] == "SOURCE_REVOKED" and field not in stale_fields:
                    continue
                if no_claims_model_error:
                    decisions.append(policy.model_error_decision(field))
                    trace.step("policy:"+field,detail={"reason":"MODEL_ERROR","verdict":"INSUFFICIENT"})
                    continue
                if stop_reason and not any(o.normalized and (o.field_key == field or
                    field == "key_ingredients" and o.field_key == "inci_list") for o in observations):
                    # A failed optional step must not turn unassessed fields into missing evidence.
                    continue
                decision = policy.decide(field, observations, product, [], [])
                decisions.append(decision)
                trace.step("policy:" + field, detail={"rules": [r.model_dump(mode="json") for r in decision.explain]})
            if not stop_reason:
                try:
                    decisions.extend(claims_audit.audit(ctx,[o for o in observations if o.source_kind == SourceKind.LISTING],observations))
                except BudgetExceeded as failure:
                    stop_reason = failure.reason
                except LLMError as failure:
                    stop_reason, error = failure.code, type(failure).__name__
            run_ref: dict[str, JsonValue] = {"id": run_id, "case_revision": job.target_revision}
            retained = publish.confirm_unchanged(run_id,job.case_id,stale_fields+[d.field_key for d in decisions]) if event and event["type"] == "SOURCE_REVOKED" else []
            for decision in decisions:
                if publish.gate(decision, run_ref, case):
                    published += 1
            status = "PARTIAL" if stop_reason and (error is None or no_claims_model_error) else "FAILED" if not published and decisions else "PARTIAL" if stop_reason else "WAITING_REVIEW" if any(
                d.review_state == ReviewState.NEEDS_REVIEW for d in decisions+retained
            ) else "WAITING_EVIDENCE" if any(d.gap for d in decisions+retained) else "COMPLETED"
    except (ValueError, RuntimeError, sqlite3.Error) as failure:
        # Record only the exception class; external errors may contain source or key material.
        error = type(failure).__name__
        stop_reason = stop_reason or "RUN_ERROR"
        status = "PARTIAL" if published else "FAILED"
        trace.step("run:stop",detail={"stop_reason": stop_reason},error=error)
    finally:
        usage = budget.usage()
        with db.transaction() as connection:
            connection.execute("UPDATE runs SET status=?,stop_reason=?,usage_json=?,error=?,finished_at=? WHERE id=?",
                               (status,stop_reason,db.dumps(usage),error,db.now_iso(),run_id))
        trace.step("run:stop",detail={"status": status,"stop_reason": stop_reason,"budget": usage})
    return run_id
