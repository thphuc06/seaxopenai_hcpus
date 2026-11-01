"""Stored explanation projection and measured execution counters."""
from collections import Counter
from datetime import datetime, timezone
from fastapi import HTTPException
from app import db
from app.api import read
from app.api.cases import review_response
from app.api.contracts import ModelCallCounts
from app.api.glassbox_contracts import BuyerExplanation, ExpertExplanation, ExplainSource, ExplainClaim, ObservabilityResponse
from app.models import DependsOn, PUBLIC_FIELDS, Role, RuleStep
from app.trace import duplicate_events


def buyer_summary(result: dict[str, db.JSON], *, visible: bool, hidden: int) -> list[str]:
    """Describe a stored decision; never recompute a verdict or expose its internals."""
    details = {
        "CONSISTENT": "The checked independent sources agree on this information.",
        "SINGLE_SOURCE": "This finding has support from one independent source.",
        "INSUFFICIENT": "There is not enough usable evidence to compare this information.",
        "UNCERTAIN": "The available evidence does not support a clear comparison.",
        "NOT_APPLICABLE": "This field does not apply to the item being compared.",
    }
    conflicts = {
        "WITHIN_SOURCE": "The same source contains conflicting statements; this is not attributed to the seller.",
        "ACROSS_SOURCES": "The checked sources disagree with one another.",
        "LISTING_VS_SOURCE": "The listing differs from the supporting source information.",
    }
    reason = details.get(str(result["verdict"]), conflicts.get(str(result["conflict_locus"]), "The stored comparison needs review."))
    if result["freshness"] == "STALE":
        reason = "Supporting evidence changed, so this finding needs to be checked again."
    evidence = "Open the quoted passages below to see the information used in this comparison." if visible else "No supporting passage is available in this view."
    if hidden:
        evidence = "Some supporting documents are visible only to reviewers."
    return [str(result["public_text"]), reason, evidence]


def explain(product_id: str, field_key: str, role: Role) -> BuyerExplanation | ExpertExplanation:
    expert = role in {Role.REVIEWER, Role.OPERATOR}
    if not expert and field_key not in PUBLIC_FIELDS:
        raise HTTPException(404, "Field not found")
    case = read.one("SELECT * FROM cases WHERE product_id=?", (product_id,))
    result = read.one("SELECT * FROM field_results WHERE case_id=? AND field_key=? AND superseded_by IS NULL", (case["id"], field_key))
    if not expert:
        citations, hidden = read.evidence(str(result["citations_json"]), Role.BUYER)
        return BuyerExplanation(product_id=product_id, field_key=field_key, public_text=str(result["public_text"]),
            summaries=buyer_summary(result, visible=bool(citations), hidden=hidden), citations=citations, hidden_citations=hidden)
    run = read.one("SELECT * FROM runs WHERE id=?", (result["run_id"],))
    sources: list[ExplainSource] = []
    claims: list[ExplainClaim] = []
    dependencies = [DependsOn.model_validate(v) for v in db.loads(str(result["depends_on_json"]))]
    for version in sorted({d.source_version_id for d in dependencies}):
        source = read.one("SELECT v.*,s.dataset_origin FROM source_versions v JOIN sources s ON s.id=v.source_id WHERE v.id=? AND s.case_id=?", (version, case["id"]))
        sources.append(ExplainSource(source_version_id=version, sha256=str(source["sha256"]), captured_at=str(source["captured_at"] or ""), origin=str(source["dataset_origin"])))
        mappings: dict[str, str] = {}
        for cached in read.rows("SELECT extraction_json FROM extraction_cache WHERE source_version_id=? ORDER BY created_at", (version,)):
            extraction = db.loads(str(cached["extraction_json"]))
            if isinstance(extraction, dict) and isinstance(extraction.get("claims"), list):
                for item in extraction["claims"]:
                    if isinstance(item, dict) and item.get("mapped_by") is not None:
                        mappings[str(item.get("id"))] = str(item["mapped_by"])
        for claim in read.rows("SELECT * FROM claims WHERE source_version_id=? AND (field_key=? OR (?='key_ingredients' AND field_key='inci_list'))", (version, field_key, field_key)):
            claims.append(ExplainClaim(source_version_id=version, passage_id=str(claim["passage_id"]), quote=claim["quote"], extractor=str(claim["extractor"]), prompt_version=str(claim["prompt_version"]), mapped_by=mappings.get(str(claim["id"]))))
    reviews = [review_response(row, int(case["revision"])) for row in read.rows("SELECT r.* FROM reviews r JOIN field_results f ON f.id=r.result_id WHERE r.case_id=? AND f.field_key=?", (case["id"], field_key))]
    checks = read.rows("SELECT output_refs FROM trace_steps WHERE run_id=? AND step='publish'", (run["id"],))
    return ExpertExplanation(product_id=product_id, field_key=field_key, result_id=str(result["id"]), trigger_event_id=str(run["trigger_event_id"] or ""), sources=sources, claims=claims,
        rules=[RuleStep.model_validate(v) for v in db.loads(str(result["explain_json"]))],
        publish_checks=["Stored publication passed" for check in checks if result["id"] in db.loads(str(check["output_refs"]))],
        chain_head=result["chain_hash"], reviews=reviews)


def observability() -> ObservabilityResponse:
    verdicts = {str(r["verdict"]): int(r["n"]) for r in read.rows("SELECT verdict,COUNT(*) n FROM field_results WHERE superseded_by IS NULL GROUP BY verdict")}
    by_step: dict[str, ModelCallCounts] = {}
    agent_stops: Counter[str] = Counter()
    gap_stops: Counter[str] = Counter()
    passed = blocked = 0
    avoided = int(read.one("SELECT COUNT(*) n FROM events WHERE outcome='NOOP'")["n"]) + duplicate_events()
    for step in read.rows("SELECT * FROM trace_steps"):
        name = str(step["step"])
        detail = db.loads(str(step["detail"] or "{}"))
        if not isinstance(detail, dict):
            continue
        if detail.get("cached"):
            avoided += 1
            by_step.setdefault(name, ModelCallCounts(live=0, replayed=0, avoided=0)).avoided += 1
        passed += name == "publish"
        blocked += name == "publish:blocked"
        if detail.get("stop_reason"):
            if name.startswith("agent:"):
                agent_stops[str(detail["stop_reason"])] += 1
            if name == "gap:stop":
                gap_stops[str(detail["stop_reason"])] += 1
        # Gateway records each actual provider attempt with a model field.
        if step["actor"] == "llm" and detail.get("model"):
            counts = by_step.setdefault(name, ModelCallCounts(live=0, replayed=0, avoided=0))
            if detail.get("replayed"):
                counts.replayed += 1
            else:
                counts.live += 1
    queue = read.one("SELECT COUNT(*) n,MIN(f.created_at) oldest FROM review_tasks t JOIN field_results f ON f.id=t.result_id WHERE t.status='OPEN'")
    age = max(0.0, (datetime.now(timezone.utc)-datetime.fromisoformat(str(queue["oldest"]).replace("Z", "+00:00"))).total_seconds()) if queue["oldest"] else None
    vocabulary = {str(r["by"]): int(r["n"]) for r in read.rows('SELECT "by",COUNT(*) n FROM vocab GROUP BY "by"')}
    return ObservabilityResponse(verdicts=verdicts, model_calls=read.model_call_counts(avoided=avoided), calls_by_step=by_step, publish_passed=passed, publish_blocked=blocked, agent_stops=dict(agent_stops), gap_stops=dict(gap_stops), vocabulary=vocabulary, review_queue_size=int(queue["n"]), oldest_review_age_s=age)
