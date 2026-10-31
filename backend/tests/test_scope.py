"""Offline scope/copy variants, independent of fixture identities and policy wiring."""
from dataclasses import replace
from itertools import permutations
from pathlib import Path
import unicodedata

import pytest
from pydantic import JsonValue

from app.models import ScopeMatch, SourceKind, Verdict
from app.pipeline.policy import decide
from app.pipeline.scope import (
    MarketRules, ScopeDecision, _market, infer_scope as infer,
    listing_copies_reference, load_market_rules,
)
from p1_helpers import observation


MARKET_RULES = MarketRules(
    country_tlds=frozenset({"vn", "fr", "uk", "co", "io", "ai", "me", "tv"}),
    generic_cctlds=frozenset({"co", "io", "ai", "me", "tv"}),
)


def infer_scope(source: dict[str, JsonValue], target: dict[str, JsonValue]) -> ScopeDecision:
    # Server configuration is an explicit external input, not a patched helper.
    return infer(source, target, market_rules=MARKET_RULES)


def product(variant: str = "240 ml", market: str = "VN") -> dict[str, JsonValue]:
    return {"id": "scope-test-product", "variant": variant, "market": market}


def page(text: str = "A product description without a named size.",
         uri: str = "https://brand.example.com/item") -> dict[str, JsonValue]:
    return {"kind": "BRAND_PAGE", "uri": uri, "source_version_id": "scope-version",
            "passages": [{"id": "scope-passage", "text": text}]}


@pytest.mark.parametrize("tld", ["co", "io", "ai", "me", "tv", "com", "zz"])
def test_generic_and_unallocated_tlds_do_not_define_market(tld: str) -> None:
    result = infer_scope(page(uri=f"https://brand.example.{tld}/item"), product())
    assert result.scope_match == ScopeMatch.MATCH
    assert not result.needs_scope_resolution


@pytest.mark.parametrize("uri,market,expected", [
    ("https://brand.example.vn/item", "VN", ScopeMatch.MATCH),
    ("https://brand.example.fr/item", "VN", ScopeMatch.MISMATCH),
    ("https://brand.example.com.vn/item", "vn", ScopeMatch.MATCH),
    ("https://brand.example.UK./item", "GB", ScopeMatch.MATCH),
    ("https://brand.example.uk/item", "UK", ScopeMatch.MATCH),
    ("https://brand.example.vn:443/fr/item?market=fr", "VN", ScopeMatch.MATCH),
    ("https://brand.example.com/path.vn", "FR", ScopeMatch.MATCH),
    ("https://brand.example.fr@brand.example.com/item", "VN", ScopeMatch.MATCH),
    ("https://[::1]/item", "VN", ScopeMatch.MATCH),
    ("https://[broken", "VN", ScopeMatch.MATCH),
    ("file:///label.fr", "VN", ScopeMatch.MATCH),
])
def test_country_inference_uses_only_http_hostname(uri: str, market: str, expected: ScopeMatch) -> None:
    assert infer_scope(page(uri=uri), product(market=market)).scope_match == expected


@pytest.mark.parametrize("kind", [SourceKind.LISTING, SourceKind.PACKAGING_IMAGE,
                                      SourceKind.NOTIFICATION_DOC, SourceKind.SELLER_UPLOAD,
                                      SourceKind.REGISTRY_RECORD])
def test_owned_evidence_ignores_domain_and_size_inference(kind: SourceKind) -> None:
    source = page("Other size: 900 ml.", "https://brand.example.fr/item")
    source["kind"] = kind.value
    assert infer_scope(source, product()).scope_match == ScopeMatch.MATCH
    source["product_id"] = "another-product"
    assert infer_scope(source, product()).scope_match == ScopeMatch.MISMATCH


@pytest.mark.parametrize("text,variant,expected", [
    ("Available in 120 ml.", "240 ml", ScopeMatch.MISMATCH),
    ("Available in 0.24 L.", "240 ml", ScopeMatch.MATCH),
    ("Available in 8 fl oz.", "237 ml", ScopeMatch.MATCH),
    ("Available in 240 g.", "240 ml", ScopeMatch.MISMATCH),
    ("Available in 240 ml (0.24 L).", "240 ml", ScopeMatch.MATCH),
    ("Available in 240 ml (242 ml nominal).", "240 ml", ScopeMatch.MATCH),
    ("No size is stated here.", "240 ml", ScopeMatch.MATCH),
    ("Available in 240 ml.", "regular", ScopeMatch.UNKNOWN),
])
def test_page_size_uses_normalization_and_shared_tolerance(text: str, variant: str,
                                                         expected: ScopeMatch) -> None:
    assert infer_scope(page(text), product(variant)).scope_match == expected


@pytest.mark.parametrize("sizes", list(permutations(("240 ml", "242 ml", "244 ml"))))
def test_size_inference_does_not_depend_on_passage_order(sizes: tuple[str, ...]) -> None:
    # The middle size matches both extremes within tolerance, but the extremes
    # disagree. A page with both extremes must always require passage scope.
    source = page()
    source["passages"] = [{"id": size, "text": size} for size in sizes]
    result = infer_scope(source, product())
    assert result.scope_match == ScopeMatch.UNKNOWN
    assert result.needs_scope_resolution


def test_multiple_sizes_require_passage_resolution_without_losing_placements() -> None:
    source = page()
    source["passages"] = [
        {"id": "small", "text": "120 ml size"},
        {"id": "large", "text": "240 ml size"},
        {"id": "description", "text": "Shared description"},
    ]
    result = infer_scope(source, product())
    assert result.scope_match == ScopeMatch.UNKNOWN
    assert result.needs_scope_resolution
    assert result.for_passage("large").scope_match == ScopeMatch.UNKNOWN
    source["passage_scopes"] = [
        {"source_version_id": "scope-version", "passage_id": pid, "scope_match": match,
         "decided_by": "AGENT" if match == "AGENT" else "CODE", "reason": "stored placement"}
        for pid, match in (("small", "MISMATCH"), ("large", "MATCH"), ("description", "AGENT"))
    ]
    result = infer_scope(source, product())
    assert not result.needs_scope_resolution
    assert result.for_passage("small").scope_match == ScopeMatch.MISMATCH
    assert result.for_passage("large").scope_match == ScopeMatch.MATCH
    assert result.for_passage("description").needs_review
    assert not result.for_passage("large").needs_review
    # Source exclusion must dominate a stored passage MATCH.
    assert replace(result, scope_match=ScopeMatch.MISMATCH).for_passage("large").scope_match == ScopeMatch.MISMATCH


@pytest.mark.parametrize("variant,other", [("137 ml", "212 ml"), ("72 g", "19 g")])
@pytest.mark.parametrize("marker", ["MULTI", "multi"])
def test_explicit_multi_variant_requires_passage_scope(variant: str, other: str, marker: str) -> None:
    target = product(variant)
    source = page()
    source["scope"] = {"product": target["id"], "variant": marker, "market": "VN"}
    source["passages"] = [{"id": "heading", "text": variant}, {"id": "description", "text": "Dry skin"},
                          {"id": "other-heading", "text": other}]
    result = infer_scope(source, target)
    assert result.scope_match == ScopeMatch.UNKNOWN and result.needs_scope_resolution
    source["passage_scopes"] = [{"source_version_id": "scope-version", "passage_id": pid,
        "scope_match": match, "decided_by": "CODE", "reason": "Stored placement"}
        for pid, match in (("heading", "MATCH"), ("description", "UNKNOWN"), ("other-heading", "MISMATCH"))]
    placed = infer_scope(source, target)
    assert placed.for_passage("heading").scope_match == ScopeMatch.MATCH
    assert placed.for_passage("other-heading").scope_match == ScopeMatch.MISMATCH
    assert placed.for_passage("description").scope_match == ScopeMatch.UNKNOWN
    source["scope"]["market"] = "FR"
    assert infer_scope(source, target).scope_match == ScopeMatch.MISMATCH


@pytest.mark.parametrize("text", ["No size given", "137 ml only"])
def test_multi_metadata_does_not_imply_single_variant_support(text: str) -> None:
    source = page(text)
    source["scope"] = {"variant": "MULTI", "market": "VN"}
    result = infer_scope(source, product("137 ml"))
    assert result.scope_match == ScopeMatch.UNKNOWN and result.needs_scope_resolution


def test_stored_placements_do_not_cross_source_versions_or_passage_identity() -> None:
    source = page("Sizes: 120 ml and 240 ml.")
    source["passage_scopes"] = [
        {"source_version_id": "old-version", "passage_id": "scope-passage", "scope_match": "MATCH"},
        {"source_version_id": "scope-version", "passage_id": "another-passage", "scope_match": "MATCH"},
    ]
    result = infer_scope(source, product())
    assert result.passage_scopes == ()
    assert result.needs_scope_resolution


@pytest.mark.parametrize("metadata", [
    {"scope": {"product": "different-product"}},
    {"scope": {"variant": "480 ml"}},
    {"scope_json": '{"market":"FR"}'},
])
def test_explicit_metadata_mismatch_is_never_overridden(metadata: dict[str, JsonValue]) -> None:
    source = page()
    source.update(metadata)
    source["kind"] = "SELLER_UPLOAD"
    assert infer_scope(source, product()).scope_match == ScopeMatch.MISMATCH


def test_explicit_market_precedes_country_domain() -> None:
    source = page(uri="https://brand.example.fr/item")
    source["scope"] = {"market": "VN"}
    assert infer_scope(source, product()).scope_match == ScopeMatch.MATCH


def test_unknown_source_kind_is_not_assumed_in_scope() -> None:
    source = page()
    source["kind"] = "UNDECLARED"
    assert infer_scope(source, product()).scope_match == ScopeMatch.UNKNOWN


def test_market_configuration_is_replaceable_without_domain_code_changes() -> None:
    # Another assigned ccTLD, outside the focused seed above.
    rules = MarketRules(frozenset({"nz"}), frozenset())
    result = infer(page(uri="https://brand.example.nz/item"), product(), market_rules=rules)
    assert result.scope_match == ScopeMatch.MISMATCH


@pytest.mark.parametrize("tld", ["co", "io", "ai", "me", "tv", "eu", "su", "zz"])
def test_default_market_data_does_not_exclude_generic_or_noncountry_hosts(tld: str) -> None:
    result = infer(page(uri=f"https://brand.example.{tld}/item"), product())
    assert result.scope_match == ScopeMatch.MATCH
    assert not result.needs_scope_resolution


@pytest.mark.parametrize("tld,market", [("nz", "NZ"), ("jp", "JP"), ("vn", "VN"), ("uk", "GB")])
def test_default_market_data_matches_country_and_excludes_other_market(tld: str, market: str) -> None:
    source = page(uri=f"https://brand.example.{tld}/item")
    assert infer(source, product(market=market)).scope_match == ScopeMatch.MATCH
    other_market = "FR" if market != "FR" else "VN"
    assert infer(source, product(market=other_market)).scope_match == ScopeMatch.MISMATCH


def test_absent_case_market_keeps_country_scope_unknown() -> None:
    assert infer_scope(page(uri="https://brand.example.fr/item"), product(market="")).scope_match == ScopeMatch.UNKNOWN


def test_market_rules_load_from_json_and_absence_is_not_a_country_guess(tmp_path: Path) -> None:
    path = tmp_path / "scope-markets.json"
    assert load_market_rules(path) is None
    assert _market("https://brand.example.fr/item", None) == (None, True)
    path.write_text('{"_about":"test configuration", "country_tlds":["fr","co"], "generic_cctlds":["co"]}',
                    encoding="utf-8")
    rules = load_market_rules(path)
    assert rules is not None
    assert _market("https://brand.example.co/item", rules) == (None, False)
    assert _market("https://brand.example.fr/item", rules) == ("FR", False)


@pytest.mark.parametrize("payload", [
    '[]', '{"country_tlds":"fr", "generic_cctlds":[]}',
    '{"country_tlds":[4], "generic_cctlds":[]}',
    '{"country_tlds":["FR"], "generic_cctlds":[]}',
    '{"country_tlds":["v1"], "generic_cctlds":[]}',
])
def test_invalid_market_data_surfaces_an_error(tmp_path: Path, payload: str) -> None:
    path = tmp_path / "invalid-market-rules.json"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError):
        load_market_rules(path)


def test_selected_agent_placement_requires_policy_review_and_mismatch_is_excluded() -> None:
    source = page("240 ml product page")
    source["passage_scopes"] = [{"source_version_id": "scope-version", "passage_id": "scope-passage",
                                  "scope_match": "AGENT", "reason": "unanchored", "decided_by": "AGENT"}]
    placement = infer_scope(source, product()).for_passage("scope-passage")
    assert placement.needs_review
    listing = observation("placed-listing", kind=SourceKind.LISTING)
    reference = observation("placed-reference", kind=SourceKind.BRAND_PAGE, scope_match=placement.scope_match)
    result = decide("volume", [listing, reference], {}, [], [])
    assert result.review_state == "NEEDS_REVIEW"
    excluded = replace(reference, scope_match=ScopeMatch.MISMATCH)
    result = decide("volume", [listing, excluded], {}, [], [])
    assert {citation.passage_id for citation in result.citations} == {listing.passage_id}


COPY = "This passage describes the texture and the daily application of the lotion."
SECOND = "The label provides the quantity and details about the packaging materials."


def test_copy_matches_every_field_passage_to_one_reference() -> None:
    listing = [COPY, SECOND]
    reference = {"family": "reference-family", "passages": [{"text": COPY}, {"text": SECOND}]}
    assert listing_copies_reference(listing, reference)
    assert reference["family"] == "reference-family"
    assert not listing_copies_reference([*listing, "A different statement about the closure and the dispenser."], reference)


def test_copy_normalizes_case_whitespace_and_unicode_without_removing_accents() -> None:
    text = "Café lotion texture information and directions for daily application."

    assert listing_copies_reference([unicodedata.normalize("NFD", text.upper())], [text])
    assert listing_copies_reference(["\n" + COPY.upper().replace(" ", "  ")], [COPY])
    assert not listing_copies_reference(["x" * 29], ["x" * 29])
    assert listing_copies_reference(["x" * 30], ["x" * 30])


def test_copy_accepts_small_edit_but_rejects_different_content() -> None:
    assert listing_copies_reference([COPY + "!"], [COPY])
    assert not listing_copies_reference([COPY], [SECOND])


def test_copy_threshold_is_inclusive_at_four_of_five_distinct_shingles() -> None:
    # This periodic text has four distinct 5-character shingles. Appending one
    # new character adds one distinct shingle: 4/5 = 0.8. Two gives 4/6.
    reference = "abcd" * 8
    assert listing_copies_reference([reference + "e"], [reference])
    assert not listing_copies_reference([reference + "ef"], [reference])


@pytest.mark.parametrize("listing,reference", [([], [COPY]), ([COPY], []), ([""], [COPY]), ([COPY], [""])])
def test_empty_or_short_text_never_proves_copy(listing: list[str], reference: list[str]) -> None:
    assert not listing_copies_reference(listing, reference)


def test_copy_does_not_concatenate_fragments_or_combine_reference_sources() -> None:
    assert not listing_copies_reference([COPY], [COPY[:35], COPY[35:]])
    reference: list[dict[str, JsonValue]] = [
        {"text": COPY, "source_id": "reference-a"},
        {"text": SECOND, "source_id": "reference-b"},
    ]
    assert not listing_copies_reference([COPY, SECOND], reference)


def test_copy_does_not_mutate_passage_data() -> None:
    listing: list[dict[str, JsonValue]] = [{"text": COPY, "family": "listing-family"}]
    before = [dict(item) for item in listing]
    assert listing_copies_reference(listing, [COPY])
    assert listing == before


def test_copy_signal_can_join_family_through_existing_policy_interface() -> None:
    listing = observation("unrelated-listing", kind=SourceKind.LISTING, quote=COPY)
    reference = observation("unrelated-reference", kind=SourceKind.BRAND_PAGE, quote=COPY)
    before = decide("volume", [listing, reference], {}, [], [])
    assert before.verdict == Verdict.SINGLE_SOURCE
    assert any(step.rule == "R7c" for step in before.explain)
    assert listing_copies_reference([listing.quote], [reference.quote])
    # Explicit family adaptation remains idempotent after automatic R7c wiring.
    copied = replace(listing, family=reference.family)
    after = decide("volume", [copied, reference], {}, [], [])
    assert after.verdict == Verdict.SINGLE_SOURCE
    assert any(step.rule == "R7" and "1 independent families" in step.detail for step in after.explain)
    assert listing.family != reference.family
