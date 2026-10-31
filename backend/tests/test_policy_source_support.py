"""A short source summary does not negate its compatible, fuller statement."""
from dataclasses import replace
from pathlib import Path
import json
import pytest
from app.models import SourceKind
from app.pipeline.policy import decide, regulatory_limits
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


def test_provisional_regulatory_table_does_not_accuse(tmp_path: Path) -> None:
    path = tmp_path/"limits.json"
    path.write_text(json.dumps({"limits":[{"inci":"Example preservative","max_percent":0.6,"status":"verify"}]}),encoding="utf-8")
    assert regulatory_limits(path=path) == {}


def test_existing_numeric_regulatory_mapping_remains_supported(tmp_path: Path) -> None:
    path = tmp_path/"limits.json"
    path.write_text(json.dumps({"limits":{"Example preservative":1.0}}),encoding="utf-8")
    assert regulatory_limits(path=path) == {"example preservative":1.0}
