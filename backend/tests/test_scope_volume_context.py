"""Main-product quantities stay distinct from promotional gift quantities."""
import pytest
from app import worker, db
from app.events.admit import admit
from app.models import Role, ScopeMatch
from app.pipeline.scope import infer_scope, volume_claim_scope
from p1_helpers import CoreDB, core_db


@pytest.mark.parametrize("main,gift,text", [
    (83,17,"Bottle 83 ml. Free gift 17 ml."),
    (121,23,"Chai 121ml; tặng mẫu 23ml"),
])
def test_reference_size_inference_excludes_only_explicit_gift(main: int, gift: int, text: str) -> None:
    source = {"kind":"BRAND_PAGE","uri":"https://example.com/item","passages":[{"id":"p","text":text}]}
    result = infer_scope(source,{"id":"item","variant":f"{main} ml","market":"VN"})
    assert result.scope_match == ScopeMatch.MATCH
    other = infer_scope(source,{"id":"item","variant":f"{gift} ml","market":"VN"})
    assert other.scope_match == ScopeMatch.MISMATCH


@pytest.mark.parametrize("text", ["Bottle 83 ml. Gift 17 ml.","Chai 83ml; tặng mẫu 17ml"])
def test_gift_quantity_does_not_create_main_volume_conflict(core_db: CoreDB, text: str) -> None:
    core_db.source("listing",kind="LISTING",text=text)
    admitted = admit(core_db.event(),role=Role.OPERATOR,actor_id="operator")
    worker.execute_job(admitted.job_id)
    finding = core_db.rows("SELECT * FROM field_results WHERE field_key='volume'")[0]
    assert finding["verdict"] == "SINGLE_SOURCE"
    citations = db.loads(finding["citations_json"])
    assert citations and all("17" not in item["excerpt"] for item in citations)
    steps = core_db.rows("SELECT detail FROM trace_steps WHERE step='scope_check'")
    assert any("GIFT_CONTEXT" in row["detail"] for row in steps)


def test_unmarked_main_volume_disagreement_is_not_hidden(core_db: CoreDB) -> None:
    core_db.source("listing",kind="LISTING",text="Bottle 83 ml. Label 97 ml.")
    admitted = admit(core_db.event(),role=Role.OPERATOR,actor_id="operator")
    worker.execute_job(admitted.job_id)
    assert core_db.rows("SELECT verdict FROM field_results WHERE field_key='volume'") == [{"verdict":"CONFLICTING"}]


@pytest.mark.parametrize("text,value,expected", [
    ("Bottle 83 ml + gift 17 ml",83,"MATCH"),
    ("Bottle 83 ml + gift 17 ml",17,"MISMATCH"),
    ("Gift 17 ml when buying 83 ml",17,"UNKNOWN"),
    ("Gift 17 ml when buying 83 ml",83,"UNKNOWN"),
    ("Gift 17 ml; Bottle 83 ml",83,"MATCH"),
    ("Gift 17 ml. Bottle 83 ml",83,"MATCH"),
    ("Bottle 83 ml. Gift 83 ml",83,"UNKNOWN"),
    ("Giftwrap bottle 83 ml",83,"MATCH"),
    ("Eighty-three milliliters",83,"MATCH"),
    ("Free gift with bottle 83 ml",83,"UNKNOWN"),
    ("Gift bag included with 83 ml bottle",83,"UNKNOWN"),
    ("No complimentary samples with 83 ml bottle",83,"UNKNOWN"),
    ("Gift wrapping is available for the 83 ml bottle",83,"UNKNOWN"),
    ("Gift set 83 ml",83,"UNKNOWN"),
    ("Tặng quà khi mua chai 83ml",83,"UNKNOWN"),
    ("Bottle 83 ml with 17 ml gift",17,"UNKNOWN"),
    ("Chai 0.083 l + TẶNG 0.017 l",17,"MISMATCH"),
])
def test_volume_context_preserves_boundaries_and_ambiguity(text: str, value: int, expected: str) -> None:
    assert volume_claim_scope(text,{"value":value,"unit":"ml"})[0] == expected


@pytest.mark.parametrize("target", [83,97])
def test_indirect_gift_wording_never_creates_scope_match(target: int) -> None:
    source = {"kind":"BRAND_PAGE","uri":"https://example.com/item",
              "passages":[{"id":"p","text":"Free gift with purchase of an 83 ml bottle"}]}
    assert infer_scope(source,{"id":"item","variant":f"{target} ml","market":"VN"}).scope_match == "UNKNOWN"


def test_ambiguous_promotion_does_not_hide_another_main_quantity(core_db: CoreDB) -> None:
    core_db.source("listing",kind="LISTING",text="Bottle 83 ml. Gift with purchase of a 97 ml bottle.")
    admitted = admit(core_db.event(),role=Role.OPERATOR,actor_id="operator")
    worker.execute_job(admitted.job_id)
    finding = core_db.rows("SELECT * FROM field_results WHERE field_key='volume'")[0]
    assert finding["verdict"] == "UNCERTAIN"
    assert any("97" in citation["excerpt"] for citation in db.loads(finding["citations_json"]))


@pytest.mark.parametrize("cue", ["tặng","quà tặng","complimentary gift","free sample gift"])
def test_overlapping_and_adjacent_gift_cues_preserve_main_quantity(cue: str) -> None:
    text = f"Bottle 83 ml + {cue} 17 ml"
    assert volume_claim_scope(text,{"value":83,"unit":"ml"})[0] == "MATCH"
    assert volume_claim_scope(text,{"value":17,"unit":"ml"})[0] == "MISMATCH"
