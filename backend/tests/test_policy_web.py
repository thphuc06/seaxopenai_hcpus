"""Retailer data can confirm but cannot introduce an adverse finding."""
from itertools import permutations

import pytest
from pydantic import JsonValue

from app.models import ReviewState, SourceKind, Verdict
from app.pipeline import policy
from p1_helpers import observation


def volume(value: int) -> dict[str, JsonValue]:
    return {"value": value, "unit": "ml"}


@pytest.mark.parametrize("reference", [False, True])
def test_retailer_disagreement_never_accuses(reference: bool) -> None:
    observations = [observation("listing", value=volume(83), kind=SourceKind.LISTING),
                    observation("retailer", value=volume(125), kind=SourceKind.WEB_PAGE)]
    if reference:
        observations.append(observation("label", value=volume(83)))
    for order in permutations(observations):
        result = policy.decide("volume", list(order), {}, [], [])
        assert result.verdict == (Verdict.CONSISTENT if reference else Verdict.UNCERTAIN)
        assert result.review_state == ReviewState.NEEDS_REVIEW
        assert result.conflict_locus is None and not result.seller_attributable
        assert all(c.source_kind != SourceKind.WEB_PAGE for c in result.citations)
        assert any(r.rule == "R9w" for r in result.explain)
        assert any(d.source_id == "retailer" for d in result.depends_on)


def test_multiple_retailer_sizes_are_ignored_without_a_finding() -> None:
    listing = observation("listing", kind=SourceKind.LISTING)
    page = observation("retailer", kind=SourceKind.WEB_PAGE)
    other = observation("retailer", value=volume(125), kind=SourceKind.WEB_PAGE, passage_id="other-passage")
    result = policy.decide("volume", [listing, page, other], {}, [], [])
    assert result.verdict == Verdict.SINGLE_SOURCE
    assert result.review_state == ReviewState.AUTO_DRAFT and result.conflict_locus is None
    assert [c.passage_id for c in result.citations] == [listing.passage_id]
    assert any(r.rule == "R4w" for r in result.explain)


def test_retailer_disagrees_with_reference_is_dropped_with_note() -> None:
    result = policy.decide("volume", [observation("label"), observation("retailer", value=volume(125), kind=SourceKind.WEB_PAGE)], {}, [], [])
    assert result.verdict == Verdict.SINGLE_SOURCE and result.conflict_locus is None
    assert result.notes and all(c.source_kind != SourceKind.WEB_PAGE for c in result.citations)


def test_web_copies_do_not_inflate_independent_support() -> None:
    text = "This source states a volume of 83 ml in the product information."
    for order in permutations([observation("reference", quote=text, family="same-family", kind=SourceKind.BRAND_PAGE),
                               observation("retailer-one", quote=text, kind=SourceKind.WEB_PAGE),
                               observation("retailer-two", quote=text, kind=SourceKind.WEB_PAGE)]):
        result = policy.decide("volume", list(order), {}, [], [])
        assert result.verdict == Verdict.SINGLE_SOURCE
        assert "one source family" in result.public_text
        assert any(r.rule == "R7w" for r in result.explain)


@pytest.mark.parametrize("web_id,brand_id", [("a-web", "z-brand"), ("z-web", "a-brand")])
def test_listing_copied_from_web_keeps_merged_family(web_id: str, brand_id: str) -> None:
    text = "Product information reports the content of this container as 83 ml."
    sources = [observation("listing", quote=text, kind=SourceKind.LISTING),
               observation(web_id, quote=text, kind=SourceKind.WEB_PAGE),
               observation(brand_id, quote=text, kind=SourceKind.BRAND_PAGE)]
    for order in permutations(sources):
        result = policy.decide("volume", list(order), {}, [], [])
        assert result.verdict == Verdict.SINGLE_SOURCE
        assert "one source family" in result.public_text
        assert any(step.rule == "R7w" for step in result.explain)


def test_non_retailer_conflict_is_preserved() -> None:
    result = policy.decide("volume", [observation("listing", kind=SourceKind.LISTING),
        observation("label", value=volume(125)), observation("retailer", value=volume(83), kind=SourceKind.WEB_PAGE)], {}, [], [])
    assert result.verdict == Verdict.CONFLICTING and result.conflict_locus == "LISTING_VS_SOURCE"
    assert all(c.source_kind != SourceKind.WEB_PAGE for c in result.citations)


def test_web_ingredient_self_conflict_is_note_only() -> None:
    first = observation("retailer", field="key_ingredients", value={"value": ["item-a"]}, kind=SourceKind.WEB_PAGE)
    second = observation("retailer", field="inci_list", value={"value": ["item-b"]}, kind=SourceKind.WEB_PAGE, passage_id="inci")
    result = policy.decide("key_ingredients", [first, second], {}, [], [])
    assert result.verdict == Verdict.INSUFFICIENT and result.conflict_locus is None
    assert any(r.rule == "R4w" for r in result.explain)


def test_split_retailer_highlights_support_listing_together() -> None:
    listing = observation("listing", field="key_ingredients", value={"value": ["a", "b"]}, kind=SourceKind.LISTING)
    first = observation("retailer", field="key_ingredients", value={"value": ["a"]}, kind=SourceKind.WEB_PAGE)
    second = observation("retailer", field="key_ingredients", value={"value": ["b"]}, kind=SourceKind.WEB_PAGE, passage_id="second")
    for order in permutations([listing, first, second]):
        result = policy.decide("key_ingredients", list(order), {}, [], [])
        assert result.verdict == Verdict.CONSISTENT and result.review_state == ReviewState.AUTO_DRAFT
        assert not any(step.rule == "R9w" for step in result.explain)


def test_fuller_retailer_skin_statement_is_used() -> None:
    listing = observation("listing", field="skin_type", value={"value": ["DRY"]}, kind=SourceKind.LISTING)
    first = observation("retailer", field="skin_type", value={"value": ["ALL"]}, kind=SourceKind.WEB_PAGE)
    second = observation("retailer", field="skin_type", value={"value": ["COMBINATION"]}, kind=SourceKind.WEB_PAGE, passage_id="second")
    result = policy.decide("skin_type", [listing, first, second], {}, [], [])
    assert result.verdict == Verdict.CONSISTENT and result.review_state == ReviewState.AUTO_DRAFT


def test_retailer_copy_is_detected_when_reference_has_extra_passages() -> None:
    text = "A reference states that the volume of this container is 83 ml."
    first = observation("brand", quote=text, kind=SourceKind.BRAND_PAGE)
    extra = observation("brand", quote="Additional technical details describe packaging dimensions and label layout for a volume of 83 ml.", kind=SourceKind.BRAND_PAGE, passage_id="extra")
    copy = observation("retailer", quote=text, kind=SourceKind.WEB_PAGE)
    for order in permutations([first, extra, copy]):
        result = policy.decide("volume", list(order), {}, [], [])
        assert "one source family" in result.public_text
        assert any(step.rule == "R7w" for step in result.explain)


def test_reference_highlights_do_not_negate_supported_retailer_highlight() -> None:
    listing = observation("listing", field="key_ingredients", value={"value": ["a"]}, kind=SourceKind.LISTING)
    retailer = observation("retailer", field="key_ingredients", value={"value": ["a"]}, kind=SourceKind.WEB_PAGE)
    reference = observation("brand", field="key_ingredients", value={"value": ["b"]}, kind=SourceKind.BRAND_PAGE)
    for order in permutations([listing, retailer, reference]):
        result = policy.decide("key_ingredients", list(order), {}, [], [])
        assert result.verdict == Verdict.CONSISTENT and result.review_state == ReviewState.AUTO_DRAFT
        assert any(c.passage_id == retailer.passage_id for c in result.citations)
        assert not any(step.rule == "R9w" for step in result.explain)
