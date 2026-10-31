"""Pure versioned decisions over normalized, provenance-bearing observations."""
from dataclasses import dataclass
from itertools import combinations
from typing import Literal
from pydantic import JsonValue
from app.models import (
    Citation, ConflictLocus, DependsOn, EvidenceLevel, FieldDecision, Freshness,
    Gap, Readability, ReviewState, RuleStep, ScopeMatch, SourceKind, SourceStatus, Verdict,
)
from app.pipeline import compare

POLICY_VERSION = "policy-v1.1"


@dataclass(frozen=True)
class SourceObs:
    source_id: str
    source_version_id: str
    source_version: int
    source_kind: SourceKind
    family: str
    status: SourceStatus
    visibility: Literal["PUBLIC", "PRIVATE"]
    scope_match: ScopeMatch
    field_key: str
    passage_id: str
    locator: str
    quote: str
    normalized: dict[str, JsonValue]
    readability: Readability = Readability.READABLE
    mapped_by: str = "seed"
    accessible: bool = True
    case_id: str | None = None
    tenant_id: str | None = None


def current_freshness() -> Freshness:
    return Freshness.CURRENT


def stale_freshness() -> Freshness:
    return Freshness.STALE


def display_value(field: str, value: JsonValue) -> str:
    if field == "volume" and isinstance(value, dict):
        return f"{value.get('value')} {value.get('unit')}"
    if field in {"skin_type", "key_ingredients", "inci_list"}:
        return ", ".join(sorted(compare.members(value))).replace("_", " ").lower()
    return str(compare.scalar(value) or "")


def decide(field_key: str, observations: list[SourceObs], product: dict[str, JsonValue],
           gaps: list[dict[str, JsonValue]], reviews: list[dict[str, JsonValue]]) -> FieldDecision:
    trail: list[RuleStep] = []
    notes: list[str] = []

    def step(rule: str, outcome: str, detail: str) -> None:
        trail.append(RuleStep(rule=rule, outcome=outcome, detail=detail))

    visible = [o for o in observations if o.accessible
               and (o.case_id is None or o.case_id == product.get("case_id"))
               and (o.tenant_id is None or o.tenant_id == product.get("tenant_id"))]
    step("R1", "FILTERED", f"{len(observations) - len(visible)} inaccessible observations excluded")
    active = [o for o in visible if o.status == SourceStatus.ACTIVE]
    step("R2", "FILTERED", f"{len(visible) - len(active)} inactive observations excluded")
    scoped = [o for o in active if o.scope_match != ScopeMatch.MISMATCH]
    step("R3", "FILTERED", f"{len(active) - len(scoped)} mismatched observations excluded")
    related = [o for o in scoped if o.field_key in {field_key, ""}
               or field_key == "key_ingredients" and o.field_key == "inci_list"]
    usable = sorted([o for o in related if o.normalized and o.quote and o.passage_id
                     and (bool(compare.members(o.normalized)) if field_key in {"skin_type", "key_ingredients"}
                          else compare.scalar(o.normalized) not in (None, ""))
                     and o.readability != Readability.UNREADABLE], key=lambda o: (o.source_id, o.passage_id))
    if any(o.readability == Readability.UNREADABLE for o in related):
        notes.append("A clearer photo of the label is needed for unreadable information.")

    def finish(verdict: Verdict, selected: list[SourceObs], *, locus: ConflictLocus | None = None,
               reason: str = "", gap: Gap | None = None) -> FieldDecision:
        scope = ScopeMatch.UNKNOWN if any(o.scope_match == ScopeMatch.UNKNOWN for o in selected) else (
            ScopeMatch.AGENT if any(o.scope_match == ScopeMatch.AGENT for o in selected) else ScopeMatch.MATCH)
        review = ReviewState.NEEDS_REVIEW if verdict == Verdict.CONFLICTING or scope == ScopeMatch.AGENT or (
            scope == ScopeMatch.UNKNOWN and field_key in {"notification_number", "responsible_company"}) else ReviewState.AUTO_DRAFT
        citations = {(o.passage_id,o.quote): Citation(passage_id=o.passage_id, source_kind=o.source_kind,
                     source_version=o.source_version, locator=o.locator, excerpt=o.quote) for o in selected}
        dependency_obs = list(selected)
        if verdict == Verdict.INSUFFICIENT:
            required = {SourceKind.NOTIFICATION_DOC} if field_key in {"notification_number", "responsible_company"} else {
                SourceKind.LISTING, SourceKind.BRAND_PAGE, SourceKind.PACKAGING_IMAGE}
            dependency_obs.extend(o for o in visible if o.source_kind in required)
        dependencies = sorted({(o.source_id, o.source_version_id) for o in dependency_obs})
        listing_values = [o for o in selected if o.source_kind == SourceKind.LISTING and o.field_key == field_key]
        displayed = listing_values or selected
        display_normalized = displayed[0].normalized if displayed else {}
        if field_key == "key_ingredients" and listing_values:
            display_normalized = {"value": sorted(set().union(*(compare.members(o.normalized) for o in listing_values)))}
        value = display_value(field_key, display_normalized) if displayed else ""
        if verdict == Verdict.CONSISTENT:
            text = f"{value} — consistent across {len({o.family for o in selected})} independent sources checked."
        elif verdict == Verdict.SINGLE_SOURCE:
            text = (f"{value} — stated by one source family only; not independently confirmed."
                    if len({o.family or o.source_id for o in selected}) == 1 else
                    f"{value} — stated in the sources checked; listing and required reference not yet compared.")
        elif verdict == Verdict.CONFLICTING:
            text = ("Conflict in source. Not attributed to the seller." if locus == ConflictLocus.WITHIN_SOURCE
                    else "Sources disagree on this field. Under review.")
        else:
            text = "Not verified: " + reason
        return FieldDecision(field_key=field_key, verdict=verdict, conflict_locus=locus, scope_match=scope,
            review_state=review, evidence_level=EvidenceLevel.PRODUCT_VERSION, seller_attributable=False,
            citations=[citations[k] for k in sorted(citations)],
            depends_on=[DependsOn(source_id=s, source_version_id=v) for s, v in dependencies],
            public_text=text, notes=notes, explain=trail, gap=gap, needs_scope_resolution=scope == ScopeMatch.UNKNOWN)

    if any(o.scope_match == ScopeMatch.UNKNOWN for o in usable):
        step("R3", "UNKNOWN", "Source scope needs confirmation")
        return finish(Verdict.UNCERTAIN, usable, reason="Source scope needs confirmation")
    adverse = [o for o in usable if o.mapped_by != "model"]
    for left, right in combinations(adverse, 2):
        if left.source_version_id != right.source_version_id:
            continue
        mismatch = not compare.agree(field_key, left.normalized, right.normalized)
        if field_key == "key_ingredients" and left.field_key == right.field_key == "key_ingredients":
            # Each highlight is a positive statement, not an exhaustive inventory.
            mismatch = False
        if field_key == "key_ingredients" and {left.field_key, right.field_key} == {"key_ingredients", "inci_list"}:
            highlight, inci = (left, right) if left.field_key == "key_ingredients" else (right, left)
            mismatch = not compare.compatible(field_key, highlight.normalized, inci.normalized)
        if mismatch:
            step("R4", "CONFLICT", "Incompatible statements in one source version; listing attribution excluded")
            return finish(Verdict.CONFLICTING, [left, right], locus=ConflictLocus.WITHIN_SOURCE)
    step("R4", "PASS", "No within-source conflict")
    if not usable:
        step("R10", "MISSING", "No usable statement")
        gap = Gap(field_key=field_key, missing_kind="SOURCE", needed_doc="Source stating this field",
                  known_ids=[], reason="No usable source statement for this field")
        return finish(Verdict.INSUFFICIENT, [], reason=gap.reason, gap=gap)
    if field_key in {"notification_number", "responsible_company"} and not any(
        o.source_kind == SourceKind.NOTIFICATION_DOC for o in usable
    ):
        step("REQ", "MISSING", "No active notification document on file")
        gap = Gap(field_key=field_key, missing_kind="NOTIFICATION_DOC", needed_doc="Active notification document",
                  known_ids=[], reason="No active notification document on file")
        return finish(Verdict.INSUFFICIENT, usable, reason=gap.reason, gap=gap)
    for left, right in combinations(adverse, 2):
        if left.source_version_id == right.source_version_id:
            continue
        listing = left if left.source_kind == SourceKind.LISTING else right if right.source_kind == SourceKind.LISTING else None
        reference = right if listing is left else left
        supported = compare.compatible(field_key, listing.normalized, reference.normalized) if listing else compare.agree(field_key, left.normalized, right.normalized)
        if not supported:
            if field_key == "key_ingredients" and reference.field_key != "inci_list":
                step("R6", "UNMENTIONED", "Highlight list is not a complete ingredient declaration")
                continue
            locus = ConflictLocus.LISTING_VS_SOURCE if listing else ConflictLocus.ACROSS_SOURCES
            step("R9", "CONFLICT", "Incompatible statements from distinct source versions")
            return finish(Verdict.CONFLICTING, [left, right], locus=locus)
    step("R5", "PASS", "Normalized statements compared")
    listing_obs = [o for o in usable if o.source_kind == SourceKind.LISTING]
    selected = usable
    if listing_obs and field_key == "key_ingredients":
        required_ingredients = set().union(*(compare.members(o.normalized) for o in listing_obs))
        supporting_versions = {o.source_version_id for o in usable if required_ingredients <= set().union(*(
            compare.members(ref.normalized) for ref in usable if ref.source_version_id == o.source_version_id))}
        selected = [o for o in usable if o.source_kind == SourceKind.LISTING or o.source_version_id in supporting_versions]
    elif listing_obs:
        selected = [o for o in usable if o.source_kind == SourceKind.LISTING or all(
            compare.compatible(field_key, claim.normalized, o.normalized) for claim in listing_obs)]
    if field_key in {"notification_number", "responsible_company"} and not any(
        o.source_kind == SourceKind.NOTIFICATION_DOC for o in selected
    ):
        step("REQ", "MISSING", "No active notification document supports the selected claim")
        gap = Gap(field_key=field_key,missing_kind="NOTIFICATION_DOC",needed_doc="Matching active notification document",
                  known_ids=[],reason="No active notification document supports this field")
        return finish(Verdict.INSUFFICIENT,selected,reason=gap.reason,gap=gap)
    families = {o.family or o.source_id for o in selected}
    step("R7", "COUNT", f"{len(families)} independent families support the claim")
    verdict = Verdict.CONSISTENT if len(families) >= 2 else Verdict.SINGLE_SOURCE
    if verdict == Verdict.CONSISTENT and field_key not in {"notification_number", "responsible_company"}:
        permitted_reference = {SourceKind.PACKAGING_IMAGE, SourceKind.BRAND_PAGE} if field_key == "volume" else {
            o.source_kind for o in selected if o.source_kind != SourceKind.LISTING}
        if not listing_obs or not any(o.source_kind in permitted_reference for o in selected):
            verdict = Verdict.SINGLE_SOURCE
            step("REQ", "MISSING", "Listing and required reference are needed for consistency")
    step("R8", verdict.value, "Agreement counted by independent family")
    return finish(verdict, selected)
