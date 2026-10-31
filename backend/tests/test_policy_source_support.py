"""A short source summary does not negate its compatible, fuller statement."""
from dataclasses import replace
import pytest
from app.models import SourceKind
from app.pipeline.policy import decide
from p1_helpers import observation


@pytest.mark.parametrize("narrow,wide", [
    (["NORMAL","OILY"],["NORMAL","COMBINATION","OILY"]),
    (["DRY"],["DRY","SENSITIVE"]),
])
def test_complete_statement_in_same_source_supports_skin_claim(narrow: list[str], wide: list[str]) -> None:
    listing = observation("listing",field="skin_type",value={"value":wide},kind=SourceKind.LISTING)
    title = observation("reference",field="skin_type",value={"value":narrow},kind=SourceKind.BRAND_PAGE)
    body = replace(title,passage_id="body",quote="A fuller description",normalized={"value":wide})
    finding = decide("skin_type",[listing,title,body],{},[],[])
    assert finding.verdict == "CONSISTENT"
    assert "body" in {citation.passage_id for citation in finding.citations}


@pytest.mark.parametrize("broad_source,mapping", [("other-reference","code"),("reference","model")])
def test_different_or_unverified_source_cannot_erase_skin_disagreement(broad_source: str, mapping: str) -> None:
    listing = observation("listing",field="skin_type",value={"value":["DRY","SENSITIVE"]},kind=SourceKind.LISTING)
    narrow = observation("reference",field="skin_type",value={"value":["DRY"]},kind=SourceKind.BRAND_PAGE)
    broad = observation(broad_source,field="skin_type",value=listing.normalized,kind=SourceKind.BRAND_PAGE,
                        passage_id="broad",quote="Broader statement",mapped_by=mapping)
    assert decide("skin_type",[listing,narrow,broad],{},[],[]).verdict == "CONFLICTING"
