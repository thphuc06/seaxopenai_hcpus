"""Grounded passage loading and explicit-size decisions for unresolved sources."""
from __future__ import annotations

from dataclasses import dataclass

from pydantic import JsonValue

from app import db
from app.agent.scope_resolution import PassageScope, ScopeOutcome
from app.context import RunContext
from app.models import ScopeMatch
from app.pipeline import compare, normalize
from app.pipeline.claims_audit import grounded_observations
from app.pipeline.fallback_extract import injection_spans
from app.pipeline.policy import SourceObs
from app.pipeline.scope import infer_scope


@dataclass(frozen=True)
class ScopePassage:
    id: str
    sv_id: str
    text: str
    section: str
    locator: str
    order: int
    sizes: list[dict[str, JsonValue]]
    decision: PassageScope
    pending: bool
    candidate_anchor: str | None
    injected: bool


@dataclass(frozen=True)
class ScopeSource:
    sv_id: str
    passages: list[ScopePassage]


@dataclass(frozen=True)
class Prepass:
    sources: list[ScopeSource]
    stop_reason: str | None = None


def current_revision(ctx: RunContext) -> bool:
    with db.transaction() as connection:
        row = connection.execute("SELECT product_id,tenant_id,revision FROM cases WHERE id=?", (ctx.case_id,)).fetchone()
        return bool(row and row["tenant_id"] == ctx.tenant_id and row["product_id"] == ctx.product.get("id")
                    and row["revision"] == ctx.case_revision)


def prepare(ctx: RunContext, observations: list[SourceObs], fields: list[str]) -> Prepass:
    """Only stored active sources authorized for this case can enter the prompt."""
    if not current_revision(ctx):
        return Prepass([], "SUPERSEDED_RUN")
    grounded = grounded_observations(ctx, observations)
    versions = sorted({obs.source_version_id for obs in grounded if obs.scope_match == ScopeMatch.UNKNOWN})
    wanted = set(fields)
    pending_ids = {obs.passage_id for obs in grounded if obs.field_key in wanted and obs.normalized}
    target = normalize.volumes_in(str(ctx.product.get("variant") or ""))
    sources: list[ScopeSource] = []
    with db.transaction() as connection:
        for sv_id in versions:
            row = connection.execute(
                "SELECT s.*,v.id AS source_version_id,v.scope_json FROM sources s "
                "JOIN source_versions v ON v.source_id=s.id WHERE v.id=? AND v.is_current=1 AND s.status='ACTIVE'",
                (sv_id,)).fetchone()
            if row is None:
                continue
            rows = [dict(p) for p in connection.execute(
                "SELECT * FROM passages WHERE source_version_id=? ORDER BY rowid", (sv_id,))]
            source: dict[str, JsonValue] = dict(row)
            source["passages"] = rows
            if infer_scope(source, ctx.product).scope_match != ScopeMatch.UNKNOWN:
                continue
            passages: list[ScopePassage] = []
            preceding: str | None = None
            previous_section: str | None = None
            for order, p in enumerate(rows):
                pid, text, section = str(p["id"]), str(p["text"]), str(p["section"] or "")
                if section != previous_section:
                    preceding = None
                sizes = normalize.volumes_in(text)
                injected = bool(injection_spans(text))
                match = ScopeMatch.UNKNOWN
                reason = "Passage has no explicit variant size"
                if sizes and len(target) == 1 and not injected:
                    match = ScopeMatch.MATCH if all(compare.same_volume(size, target[0]) for size in sizes) else ScopeMatch.MISMATCH
                    reason = "All explicit sizes match the variant" if match == ScopeMatch.MATCH else "An explicit size differs from the variant"
                elif injected:
                    reason = "Instruction-bearing passage requires review"
                elif len(target) != 1:
                    reason = "Case variant has no unambiguous size"
                candidate = preceding if section else None
                pending = not sizes and not injected and pid in pending_ids and len(target) == 1
                decision = PassageScope(pid, sv_id, match, "CODE", None, reason)
                passages.append(ScopePassage(pid, sv_id, text, section, str(p["locator"]), order,
                                             sizes, decision, pending, candidate, injected))
                if sizes:
                    # Even an unusable size statement blocks an older anchor.
                    preceding = pid
                previous_section = section
            sources.append(ScopeSource(sv_id, passages))
    return Prepass(sources)


def persist(ctx: RunContext, decisions: list[PassageScope]) -> bool:
    """Recheck revision and source validity atomically before storing placements."""
    with db.transaction() as connection:
        case = connection.execute("SELECT revision,tenant_id,product_id FROM cases WHERE id=?", (ctx.case_id,)).fetchone()
        if not case or (case["revision"], case["tenant_id"], case["product_id"]) != (
                ctx.case_revision, ctx.tenant_id, ctx.product.get("id")):
            return False
        for decision in decisions:
            source = connection.execute(
                "SELECT s.case_id,s.product_id,s.visibility FROM passages p "
                "JOIN source_versions v ON v.id=p.source_version_id JOIN sources s ON s.id=v.source_id "
                "WHERE p.id=? AND v.id=? AND v.is_current=1 AND s.status='ACTIVE'",
                (decision.passage_id, decision.sv_id)).fetchone()
            if not source or not (source["case_id"] == ctx.case_id or (
                    source["case_id"] is None and source["visibility"] == "PUBLIC" and source["product_id"] == ctx.product.get("id"))):
                return False
        for decision in decisions:
            connection.execute(
                "INSERT INTO passage_scopes(source_version_id,passage_id,scope_match,reason,decided_by,run_id,created_at) "
                "VALUES(?,?,?,?,?,?,?) ON CONFLICT(source_version_id,passage_id) DO UPDATE SET "
                "scope_match=excluded.scope_match,reason=excluded.reason,decided_by=excluded.decided_by,run_id=excluded.run_id,created_at=excluded.created_at",
                (decision.sv_id, decision.passage_id, decision.scope_match.value, decision.reason,
                 decision.decided_by, ctx.run_id, db.now_iso()))
    return True


def resolve_all(ctx: RunContext, observations: list[SourceObs], fields: list[str]) -> ScopeOutcome:
    prepared = prepare(ctx, observations, fields)
    decisions = [p.decision for source in prepared.sources for p in source.passages]
    ctx.trace.step("scope:code_prepass", input_refs=[source.sv_id for source in prepared.sources],
                   output_refs=[d.passage_id for d in decisions],
                   detail={"mode": "FALLBACK" if ctx.mode == "fallback" else ctx.mode.upper(),
                           "pending": sum(p.pending for source in prepared.sources for p in source.passages),
                           "ignored_instructions_detected": any(p.injected for source in prepared.sources for p in source.passages)})
    if prepared.stop_reason or not persist(ctx, decisions):
        return ScopeOutcome([], False, prepared.stop_reason or "SUPERSEDED_RUN", "Scope decisions were not stored")
    return ScopeOutcome(decisions, any(d.scope_match != ScopeMatch.UNKNOWN for d in decisions), None,
                        "Explicit-size scope decisions stored")
