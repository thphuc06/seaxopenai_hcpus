"""Revision-bound review publication with independent synthetic inputs."""
import pytest
from app import db
from app.models import Role, Verdict, ConflictLocus
from app.events.admit import admit
from app.pipeline import policy, publish
from p1_helpers import CoreDB, core_db


def prepare(core_db: CoreDB) -> str:
    obs = core_db.source(text="Container: 83 ml.")
    decision = policy.decide("volume",[obs],{},[],[])
    assert publish.gate(decision,core_db.run(),{"id":core_db.case_id})
    return str(core_db.rows("SELECT id FROM field_results")[0]["id"])


@pytest.mark.parametrize("decision", ["APPROVE","REJECT"])
def test_review_publishes_and_revision_supersedes(core_db: CoreDB, decision: str) -> None:
    result = prepare(core_db)
    publish.review(core_db.case_id,result,0,decision,"Checked source",None,"reviewer")
    current = core_db.rows("SELECT * FROM field_results WHERE superseded_by IS NULL")[0]
    assert current["review_state"] == "REVIEWED"
    assert current["verdict"] == ("INSUFFICIENT" if decision == "REJECT" else "SINGLE_SOURCE")
    admit(core_db.event(),role=Role.OPERATOR,actor_id="operator")
    before = core_db.dump()
    with pytest.raises(publish.ReviewError) as caught:
        publish.review(core_db.case_id,str(current["id"]),0,"APPROVE","Old review",None,"reviewer")
    assert caught.value.status == 409
    assert core_db.dump() == before


@pytest.mark.parametrize("override,reason", [
    ({"verdict":"CONSISTENT","citations":[],"public_text":"Sources agree."},"NO_CITATION"),
    ({"verdict":"INSUFFICIENT","citations":[],"public_text":"A safe item"},"FORBIDDEN_WORDING"),
])
def test_override_gate_rolls_back_all_rows(core_db: CoreDB, override: dict[str, db.JSON], reason: str) -> None:
    result = prepare(core_db)
    before = core_db.dump()
    with pytest.raises(publish.ReviewError,match=reason):
        publish.review(core_db.case_id,result,0,"OVERRIDE","Correction",override,"reviewer")
    assert core_db.dump() == before


@pytest.mark.parametrize("family", ["alcohol","fragrance"])
def test_claim_model_mapping_cannot_accuse(core_db: CoreDB, family: str) -> None:
    from dataclasses import replace
    obs = core_db.source()
    claim = replace(obs,field_key="claim:free_from:"+family,normalized={"value":family},mapped_by="model")
    inci = replace(obs,field_key="inci_list",normalized={"value":["Alcohol","Parfum"]})
    result = policy.decide(claim.field_key,[claim,inci],{},[],[])
    assert result.verdict == Verdict.UNCERTAIN
    assert result.review_state == "NEEDS_REVIEW"
    assert any(step.rule == "CL" for step in result.explain)


@pytest.mark.parametrize("scope", ["UNKNOWN","AGENT"])
def test_claim_scope_cap_matches_final_trail(core_db: CoreDB, scope: str) -> None:
    from dataclasses import replace
    from app.models import ScopeMatch
    obs = core_db.source()
    key = "claim:free_from:fragrance"
    claim = replace(obs,field_key=key,normalized={"value":"fragrance"})
    inci = replace(obs,field_key="inci_list",normalized={"value":["Parfum"]},scope_match=ScopeMatch(scope))
    result = policy.decide(key,[claim,inci],{},[],[])
    assert result.verdict == Verdict.UNCERTAIN and result.review_state == "NEEDS_REVIEW"
    assert any(step.rule == "R3" and step.outcome == "UNCERTAIN" for step in result.explain)
    assert [step.outcome for step in result.explain if step.rule == "CL"] == ["UNCERTAIN"]


@pytest.mark.parametrize("key", ["claim:treatment:skin","claim:free_from:fragrance"])
def test_claim_without_citable_evidence_still_requires_review(key: str) -> None:
    result = policy.decide(key,[],{},[],[])
    assert result.verdict == Verdict.INSUFFICIENT and result.review_state == "NEEDS_REVIEW"
    assert result.citations == []


@pytest.mark.parametrize("ingredient", ["Target A","Target B"])
def test_inci_order_does_not_infer_sub_one_percent_limit(ingredient: str) -> None:
    assert policy.concentration_bound(["Water","Capped",ingredient],ingredient,{"capped":0.3}) == 1.0
    assert policy.concentration_bound(["Water",ingredient,"Capped"],ingredient,{"capped":0.3}) is None


def test_seed_claim_conflict_has_both_citations(core_db: CoreDB) -> None:
    from dataclasses import replace
    obs = core_db.source()
    claim = replace(obs,field_key="claim:free_from:fragrance",normalized={"value":"fragrance"})
    inci = replace(obs,passage_id="other-passage",field_key="inci_list",normalized={"value":["Water","Parfum"]})
    decision = policy.decide(claim.field_key,[claim,inci],{},[],[])
    assert decision.verdict == "CONFLICTING"
    assert decision.review_state == "NEEDS_REVIEW"
    assert len(decision.citations) == 2


@pytest.mark.parametrize("change", ["empty","unreadable","unknown"])
def test_claim_ineligible_reference_cannot_confirm_or_accuse(core_db: CoreDB, change: str) -> None:
    from dataclasses import replace
    from app.models import Readability, ScopeMatch
    obs = core_db.source()
    claim = replace(obs,field_key="claim:free_from:fragrance",normalized={"value":"fragrance"})
    inci = replace(obs,field_key="inci_list",normalized={"value":["Parfum"]})
    if change == "empty":
        inci = replace(inci,normalized={})
    elif change == "unreadable":
        inci = replace(inci,readability=Readability.UNREADABLE)
    else:
        inci = replace(inci,scope_match=ScopeMatch.UNKNOWN)
    assert policy.decide(claim.field_key,[claim,inci],{},[],[]).verdict == "UNCERTAIN"


def test_unrelated_model_reference_does_not_erase_seed_conflict(core_db: CoreDB) -> None:
    from dataclasses import replace
    obs = core_db.source()
    claim = replace(obs,field_key="claim:free_from:alcohol",normalized={"value":"alcohol"})
    inci = replace(obs,field_key="inci_list",normalized={"value":["ALCOHOL DENAT"],"items":["Alcohol Denat."]})
    other = replace(inci,source_id="other",mapped_by="model",normalized={"value":["Water"]})
    assert policy.decide(claim.field_key,[claim,inci,other],{},[],[]).verdict == "CONFLICTING"


def test_review_approve_insufficient_keeps_open_request(core_db: CoreDB) -> None:
    finding = policy.decide("volume",[],{},[],[])
    assert publish.gate(finding,core_db.run(),{"id":core_db.case_id})
    result = core_db.rows("SELECT id FROM field_results")[0]["id"]
    publish.review(core_db.case_id,str(result),0,"APPROVE","Missing evidence confirmed",None,"reviewer")
    assert {r["status"] for r in core_db.rows("SELECT status FROM evidence_requests")} == {"OPEN"}


def test_override_citation_dependency_stales_on_revoke(core_db: CoreDB) -> None:
    result = prepare(core_db)
    other = core_db.source("different-source",text="Volume: 83 ml.")
    cited = policy.decide("volume",[other],{},[],[])
    override = {"verdict":"SINGLE_SOURCE","public_text":"Stated in the source checked.",
                "citations":[c.model_dump(mode="json") for c in cited.citations]}
    publish.review(core_db.case_id,result,0,"OVERRIDE","Use another passage",override,"reviewer")
    event = core_db.event("SOURCE_REVOKED",resource_kind="SOURCE",resource_id=other.source_id)
    assert admit(event,role=Role.OPERATOR,actor_id="operator").stale_fields == ["volume"]


def test_reconfirmed_result_can_be_reviewed_at_current_revision(core_db: CoreDB) -> None:
    obs = core_db.source()
    finding = policy.decide("volume",[obs],{},[],[])
    assert publish.gate(finding,core_db.run(),{"id":core_db.case_id})
    identity = core_db.rows("SELECT id FROM field_results")[0]["id"]
    admit(core_db.event(),role=Role.OPERATOR,actor_id="operator")
    assert publish.gate(finding,core_db.run(1),{"id":core_db.case_id})
    publish.review(core_db.case_id,str(identity),1,"APPROVE","Current confirmation",None,"reviewer")
    assert core_db.rows("SELECT case_revision FROM reviews")[0]["case_revision"] == 1


@pytest.mark.parametrize("choice", ["OVERRIDE","REJECT"])
def test_review_clears_obsolete_conflict_locus(core_db: CoreDB, choice: str) -> None:
    decision = policy.decide("volume",[core_db.source()],{},[],[])
    decision = decision.model_copy(update={"verdict":Verdict.CONFLICTING,"conflict_locus":ConflictLocus.WITHIN_SOURCE})
    override = {"verdict":"CONSISTENT","citations":[c.model_dump(mode="json") for c in decision.citations],"public_text":"Sources agree."} if choice == "OVERRIDE" else None
    assert policy.reviewed_decision(decision,choice,override).conflict_locus is None
