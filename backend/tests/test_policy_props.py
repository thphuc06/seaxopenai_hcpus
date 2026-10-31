"""P1-1b spec-derived properties; no fixture/gold reads or app replacement.

The isolated observation constructor now matches P1's S1 SourceObs contract.
All expectations were authored from docs06 before the implementation was run.
"""
from itertools import permutations

import pytest
from pydantic import JsonValue

from app.models import ConflictLocus, ReviewState, Verdict
from app.pipeline import compare, normalize, policy

pytestmark = pytest.mark.phase(1)


@pytest.mark.parametrize("raw", ["473ml", "473 ml", "16 fl oz", "0.473 L"])
def test_volume_unit_variants(raw: str) -> None:
    """R5: all four representations agree within 1%, not exact float equality."""
    value = normalize.normalize("volume", raw)
    assert value is not None, raw
    expected: dict[str, JsonValue] = {"value": 473.0, "unit": "ml"}
    assert compare.same_volume(value, expected), raw
    assert compare.compatible("volume", value, expected), raw
    assert compare.agree("volume", value, expected), raw


@pytest.mark.parametrize("base", [37.0, 473.0, 812.0])
@pytest.mark.parametrize("ratio,expected", [(1.0, True), (1.005, True), (1.03, False)])
def test_volume_tolerance_is_symmetric_and_scale_independent(base: float, ratio: float, expected: bool) -> None:
    """R5: cases comfortably inside/outside 1%, avoiding boundary convention ambiguity."""
    left: dict[str, JsonValue] = {"value": base, "unit": "ml"}
    right: dict[str, JsonValue] = {"value": base * ratio, "unit": "ml"}
    assert compare.same_volume(left, right) is expected
    assert compare.same_volume(right, left) is expected
    assert compare.agree("volume", left, right) is expected
    assert compare.agree("volume", right, left) is expected


@pytest.mark.parametrize("phrase,expected", [
    pytest.param("da khô", {"DRY"}, id="dry-vi"),
    pytest.param("dry skin", {"DRY"}, id="dry-en"),
    pytest.param("da thường đến da dầu", {"NORMAL", "COMBINATION", "OILY"}, id="range-vi"),
    pytest.param("normal to oily", {"NORMAL", "COMBINATION", "OILY"}, id="range-en"),
    pytest.param("mọi loại da", {"ALL"}, id="all-vi"),
    pytest.param("all skin types", {"ALL"}, id="all-en"),
])
def test_skin_seed_meaning_survives_language_and_whitespace(phrase: str, expected: set[str]) -> None:
    """R5; docs04/dataset §6 define the explicit bilingual range convention."""
    assert normalize.skin_types_in(phrase) == expected
    assert normalize.skin_types_in(f"  {phrase.upper()}  ") == expected
    value = normalize.normalize("skin_type", phrase)
    assert value is not None
    assert compare.agree("skin_type", value, value)


@pytest.mark.parametrize("claim,reference,supported,agreement", [
    pytest.param("mọi loại da", "dry skin", False, True, id="all-to-dry"),
    pytest.param("da khô", "all skin types", True, True, id="dry-to-all"),
    pytest.param("dry skin", "da thường đến da dầu", False, False, id="dry-to-range"),
    pytest.param("normal to oily", "da thường đến da dầu", True, True, id="range-bilingual"),
])
def test_skin_support_is_directional_but_reference_agreement_is_symmetric(
    claim: str, reference: str, supported: bool, agreement: bool,
) -> None:
    """R5: listing ALL is stronger than DRY; reference agreement accepts either direction."""
    left = normalize.normalize("skin_type", claim)
    right = normalize.normalize("skin_type", reference)
    assert left is not None and right is not None
    assert compare.compatible("skin_type", left, right) is supported
    assert compare.agree("skin_type", left, right) is agreement
    assert compare.agree("skin_type", right, left) is agreement


@pytest.mark.parametrize("stem", ["Moc River", "Amber Harbour"])
@pytest.mark.parametrize("template", ["Cty TNHH {}", "Công ty CP {}", "{} JSC", "{} Co., Ltd"])
def test_company_legal_forms_preserve_identity_without_merging_distinct_names(stem: str, template: str) -> None:
    """R5 exact after normalization; legal-form removal follows P2 §S1 / dataset §6."""
    raw = template.format(stem)
    canonical = normalize.company_key(stem)
    assert canonical
    assert normalize.company_key(raw) == canonical
    assert normalize.company_key(f"  {raw.upper()}  ") == canonical
    assert normalize.company_key(template.format(stem + " Trading")) != canonical
    left = normalize.normalize("responsible_company", raw)
    right = normalize.normalize("responsible_company", stem)
    assert left is not None and right is not None
    assert compare.agree("responsible_company", left, right)


def observation(source: str, family: str, kind: str, passage: str, volume: float) -> policy.SourceObs:
    """Proposed test-only binding, pending P1 SourceObs fields; never patches app code."""
    values: dict[str, JsonValue] = {
        "source_id": source, "source_version_id": source + "-v1", "source_version": 1,
        "source_kind": kind, "family": family, "status": "ACTIVE", "visibility": "PUBLIC",
        "scope_match": "MATCH", "field_key": "volume", "passage_id": passage,
        "locator": "specification/" + passage, "quote": f"Volume: {volume} ml",
        "normalized": {"value": volume, "unit": "ml"}, "readability": "READABLE",
    }
    return policy.SourceObs(**values)


# No pipeline output was consulted. Expected outcomes are fixed by docs06:
# R7 shared family -> SINGLE_SOURCE; R8 two families -> CONSISTENT;
# R9 reference disagreement -> ACROSS_SOURCES (explicit P1-1b requirement);
# R4 two incompatible passages in one version -> WITHIN_SOURCE before listing comparison.
SCENARIOS = [
    pytest.param([
        ("listing", "copied-brand", "LISTING", "p1", 473.0),
        ("brand", "copied-brand", "BRAND_PAGE", "p2", 473.0),
        ("brand", "copied-brand", "BRAND_PAGE", "p3", 473.0),
    ], Verdict.SINGLE_SOURCE, None, id="R7-copied-family"),
    pytest.param([
        ("listing", "seller", "LISTING", "p1", 473.0),
        ("brand", "brand", "BRAND_PAGE", "p2", 473.0),
        ("label", "packaging", "PACKAGING_IMAGE", "p3", 473.0),
    ], Verdict.CONSISTENT, None, id="R8-independent"),
    pytest.param([
        ("brand", "brand", "BRAND_PAGE", "p1", 473.0),
        ("label", "packaging", "PACKAGING_IMAGE", "p2", 620.0),
    ], Verdict.CONFLICTING, ConflictLocus.ACROSS_SOURCES, id="R9-reference-conflict"),
    pytest.param([
        ("listing", "seller", "LISTING", "p1", 473.0),
        ("brand", "brand", "BRAND_PAGE", "p2", 473.0),
        ("brand", "brand", "BRAND_PAGE", "p3", 620.0),
    ], Verdict.CONFLICTING, ConflictLocus.WITHIN_SOURCE, id="R4-self-conflict-first"),
]


@pytest.mark.parametrize("rows,verdict,locus", SCENARIOS)
def test_policy_decision_is_invariant_under_passage_order(
    rows: list[tuple[str, str, str, str, float]], verdict: Verdict, locus: ConflictLocus | None,
) -> None:
    product: dict[str, JsonValue] = {
        "id": "unrelated-probe", "name": "Probe wash", "brand": "Probe maker",
        "variant": "473 ml", "market": "VN", "version": "1", "web": {},
    }
    observations = [observation(*row) for row in rows]
    baseline = None
    for order in permutations(observations):
        decision = policy.decide("volume", list(order), product, [], [])
        assert decision.verdict == verdict, rows
        assert decision.conflict_locus == locus, rows
        if locus is not None:
            assert decision.review_state == ReviewState.NEEDS_REVIEW
            assert decision.seller_attributable is False
        assert decision.citations
        assert {citation.passage_id for citation in decision.citations} <= {row[3] for row in rows}
        semantic_result = (
            decision.verdict, decision.conflict_locus, decision.review_state,
            decision.seller_attributable, decision.scope_match,
            frozenset(c.passage_id for c in decision.citations),
            frozenset((d.source_id, d.source_version_id) for d in decision.depends_on),
        )
        if baseline is None:
            baseline = semantic_result
        assert semantic_result == baseline, rows


def test_no_observations_produces_missing_evidence_gap() -> None:
    """R10 has a usable existing signature even before SourceObs fields are defined."""
    result = policy.decide("volume", [], {"id": "empty-evidence-probe"}, [], [])
    assert result.verdict == Verdict.INSUFFICIENT
    assert result.gap is not None
    assert result.gap.field_key == "volume"
    assert result.citations == []
