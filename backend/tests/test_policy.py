"""docs06 rules on normalized values unrelated to the demo dataset."""
from dataclasses import replace
from itertools import permutations
import pytest
from app.models import ConflictLocus, Readability, ReviewState, ScopeMatch, SourceKind, SourceStatus, Verdict
from app.pipeline.policy import decide
from app.pipeline.compare import same_volume
from p1_helpers import observation

pytestmark = pytest.mark.phase(1)


@pytest.mark.parametrize("excluded", [
    {"accessible":False}, {"case_id":"other-case"}, {"tenant_id":"other-tenant"},
    {"status":SourceStatus.REVOKED}, {"status":SourceStatus.SUPERSEDED}, {"scope_match":ScopeMatch.MISMATCH},
])
def test_rules_1_to_3_exclude_unusable_sources(excluded: dict[str, object]) -> None:
    result = decide("volume",[observation(**excluded)],{"case_id":"case","tenant_id":"tenant"},[],[])
    assert result.verdict == Verdict.INSUFFICIENT
    assert not result.citations
    assert result.gap


def test_unknown_scope_cannot_create_an_accusation() -> None:
    claims = [observation("one"),observation("two",value={"value":129,"unit":"ml"},scope_match=ScopeMatch.UNKNOWN)]
    result = decide("volume",claims,{},[],[])
    assert result.verdict == Verdict.UNCERTAIN
    assert result.scope_match == ScopeMatch.UNKNOWN
    assert result.needs_scope_resolution


def test_self_conflict_precedes_listing_comparison() -> None:
    first = observation("page",field="skin_type",value={"value":["DRY"]},kind=SourceKind.BRAND_PAGE)
    second = replace(first,passage_id="body",normalized={"value":["NORMAL","OILY"]})
    listing = observation("listing",field="skin_type",value={"value":["OILY"]},kind=SourceKind.LISTING)
    for claims in permutations([first,second,listing]):
        result = decide("skin_type",list(claims),{},[],[])
        assert result.verdict == Verdict.CONFLICTING
        assert result.conflict_locus == ConflictLocus.WITHIN_SOURCE
        assert result.review_state == ReviewState.NEEDS_REVIEW
        assert not result.seller_attributable
        assert {c.passage_id for c in result.citations} == {first.passage_id,second.passage_id}


def test_highlights_are_positive_statements_not_exhaustive_lists() -> None:
    listing = observation("listing","key_ingredients",{"value":["glycerin","aqua"]},SourceKind.LISTING)
    first = observation("page","key_ingredients",{"value":["glycerin"]},SourceKind.BRAND_PAGE)
    second = replace(first,passage_id="page-more",normalized={"value":["aqua"]})
    result = decide("key_ingredients",[listing,first,second],{},[],[])
    assert result.verdict == Verdict.CONSISTENT
    assert len(result.citations) == 3


def test_highlight_absent_from_own_full_inci_is_a_self_conflict() -> None:
    highlight = observation("page","key_ingredients",{"value":["glycerin"]},SourceKind.BRAND_PAGE)
    inci = replace(highlight,passage_id="inci",field_key="inci_list",normalized={"value":["aqua"]})
    result = decide("key_ingredients",[highlight,inci],{},[],[])
    assert result.verdict == Verdict.CONFLICTING
    assert result.conflict_locus == ConflictLocus.WITHIN_SOURCE


def test_unmentioned_ingredient_does_not_accuse() -> None:
    listing = observation("listing","key_ingredients",{"value":["glycerin"]},SourceKind.LISTING)
    page = observation("page","key_ingredients",{"value":["aqua"]},SourceKind.BRAND_PAGE)
    result = decide("key_ingredients",[listing,page],{},[],[])
    assert result.verdict == Verdict.SINGLE_SOURCE
    assert not result.seller_attributable
    assert [c.passage_id for c in result.citations] == [listing.passage_id]


def test_model_mapping_never_raises_a_conflict() -> None:
    listing = observation("listing","key_ingredients",{"value":["glycerin"]},SourceKind.LISTING,mapped_by="model")
    inci = observation("label","inci_list",{"value":["aqua"]})
    result = decide("key_ingredients",[listing,inci],{},[],[])
    assert result.verdict != Verdict.CONFLICTING
    assert not result.seller_attributable


@pytest.mark.parametrize("field,value", [("notification_number","XY123"),("responsible_company","alder works")])
def test_active_notification_requirement_and_revoke(field: str, value: str) -> None:
    label = observation("label",field,{"value":value})
    document = observation("doc",field,{"value":value},SourceKind.NOTIFICATION_DOC)
    result = decide(field,[label,document],{},[],[])
    assert result.verdict == Verdict.CONSISTENT
    result = decide(field,[label,replace(document,status=SourceStatus.REVOKED)],{},[],[])
    assert result.verdict == Verdict.INSUFFICIENT
    assert result.gap and result.gap.missing_kind == "NOTIFICATION_DOC"
    assert {d.source_id for d in result.depends_on} == {"label","doc"}
    assert all(c.source_kind != SourceKind.NOTIFICATION_DOC for c in result.citations)


def test_volume_requires_listing_and_label_or_brand_for_consistency() -> None:
    result = decide("volume",[observation("label"),observation("page",kind=SourceKind.BRAND_PAGE)],{},[],[])
    assert result.verdict != Verdict.CONSISTENT
    result = decide("volume",[observation("listing",kind=SourceKind.LISTING),observation("label")],{},[],[])
    assert result.verdict == Verdict.CONSISTENT
    assert result.public_text.startswith("83 ml")


def test_unreadable_does_not_erase_readable_support() -> None:
    readable = observation("page",kind=SourceKind.BRAND_PAGE)
    unreadable = observation("image",readability=Readability.UNREADABLE,normalized={})
    result = decide("volume",[readable,unreadable],{},[],[])
    assert result.verdict == Verdict.SINGLE_SOURCE
    assert result.notes
    assert [c.passage_id for c in result.citations] == [readable.passage_id]


def test_empty_normalized_ingredient_set_is_not_support() -> None:
    result = decide("key_ingredients",[observation("page","key_ingredients",{"value":[],"unknown":["unmapped"]})],{},[],[])
    assert result.verdict == Verdict.INSUFFICIENT
    assert result.gap


def test_dependency_set_is_field_specific() -> None:
    volume = observation()
    doc = observation("doc","notification_number",{"value":"ZZ20"},SourceKind.NOTIFICATION_DOC)
    sentinel = replace(doc,field_key="",normalized={},quote="",passage_id="")
    result = decide("volume",[volume,doc,sentinel],{},[],[])
    assert {d.source_id for d in result.depends_on} == {volume.source_id}


@pytest.mark.parametrize("listing_id,reference_id", [("a-listing","z-brand"),("z-listing","a-brand")])
def test_display_uses_supported_listing_value_not_broader_reference(listing_id: str, reference_id: str) -> None:
    listing = observation(listing_id,"skin_type",{"value":["DRY"]},SourceKind.LISTING)
    page = observation(reference_id,"skin_type",{"value":["ALL"]},SourceKind.BRAND_PAGE)
    result = decide("skin_type",[page,listing],{},[],[])
    assert result.verdict == Verdict.CONSISTENT
    assert result.public_text.startswith("dry —")
    listing = replace(listing,field_key="key_ingredients",normalized={"value":["glycerin"]})
    page = replace(page,field_key="inci_list",normalized={"value":["aqua","glycerin"]})
    result = decide("key_ingredients",[page,listing],{},[],[])
    assert result.verdict == Verdict.CONSISTENT
    assert result.public_text.startswith("glycerin —")


def test_notification_requirement_applies_to_final_cited_support() -> None:
    listing = observation("listing","notification_number",{"value":"NX83"},SourceKind.LISTING)
    label = observation("label","notification_number",{"value":"NX83"})
    doc = observation("doc","notification_number",{"value":"NX99"},SourceKind.NOTIFICATION_DOC,mapped_by="model")
    result = decide("notification_number",[listing,label,doc],{},[],[])
    assert result.verdict == Verdict.INSUFFICIENT
    assert result.gap and result.gap.missing_kind == "NOTIFICATION_DOC"


def test_missing_listing_does_not_claim_two_families_are_one() -> None:
    result = decide("volume",[observation("label"),observation("page",kind=SourceKind.BRAND_PAGE)],{},[],[])
    assert result.verdict == Verdict.SINGLE_SOURCE
    assert "one source family" not in result.public_text
    assert "listing" in result.public_text


def test_distinct_quotes_in_one_passage_both_survive_conflict_evidence() -> None:
    first = observation(quote="83 ml")
    second = replace(first,normalized={"value":129,"unit":"ml"},quote="129 ml")
    result = decide("volume",[first,second],{},[],[])
    assert result.conflict_locus == ConflictLocus.WITHIN_SOURCE
    assert {c.excerpt for c in result.citations} == {"83 ml","129 ml"}


@pytest.mark.parametrize("value", [{"value":83},{"value":83,"unit":"unrecognized"},{"value":True,"unit":"ml"}])
def test_volume_requires_a_valid_canonical_measure(value: dict[str, object]) -> None:
    assert not same_volume(value,value)
