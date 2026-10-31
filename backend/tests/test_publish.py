from dataclasses import replace
import pytest
from app import db
from app.models import Citation, DependsOn
from app.pipeline import policy, publish
from p1_helpers import CoreDB, core_db

pytestmark = pytest.mark.phase(1)


@pytest.mark.parametrize("failure", ["NO_CITATION","INVALID_LOCATOR","INACTIVE_SOURCE","FORBIDDEN_WORDING","SUPERSEDED_RUN","INVALID_DEPENDENCY"])
def test_gate_rejects_each_failure_without_publishing(core_db: CoreDB, failure: str) -> None:
    obs = core_db.source()
    decision = policy.decide("volume",[obs],{},[],[])
    run = core_db.run()
    if failure == "NO_CITATION":
        decision = decision.model_copy(update={"citations":[]})
    elif failure == "INVALID_LOCATOR":
        decision = decision.model_copy(update={"citations":[decision.citations[0].model_copy(update={"excerpt":"83 ml invented"})]})
    elif failure == "INACTIVE_SOURCE":
        with db.transaction() as connection:
            connection.execute("UPDATE sources SET status='REVOKED'")
    elif failure == "FORBIDDEN_WORDING":
        decision = decision.model_copy(update={"public_text":"verified product"})
    elif failure == "SUPERSEDED_RUN":
        with db.transaction() as connection:
            connection.execute("UPDATE cases SET revision=2")
    else:
        decision = decision.model_copy(update={"depends_on":[DependsOn(source_id="missing",source_version_id="missing")]})
    assert not publish.gate(decision,run,{"id":core_db.case_id})
    assert not core_db.rows("SELECT * FROM field_results")
    assert not core_db.rows("SELECT * FROM gaps")
    blocked = core_db.rows("SELECT detail FROM trace_steps WHERE step='publish:blocked'")
    assert db.loads(blocked[0]["detail"])["reason"] == failure


@pytest.mark.parametrize("part,value", [("passage_id","absent"),("locator","wrong"),("source_version",27),("source_kind","BRAND_PAGE")])
def test_citation_identity_is_bound_to_stored_passage(core_db: CoreDB, part: str, value: str | int) -> None:
    decision = policy.decide("volume",[core_db.source()],{},[],[])
    altered = decision.citations[0].model_dump()
    altered[part] = value
    decision = decision.model_copy(update={"citations":[Citation.model_validate(altered)]})
    assert not publish.gate(decision,core_db.run(),{"id":core_db.case_id})
    assert not core_db.rows("SELECT * FROM field_results")


def test_gate_normalizes_unicode_and_whitespace_but_not_noncontiguous_quotes(core_db: CoreDB) -> None:
    obs = core_db.source(text="Dung tích:  83\nml. Extra words.")
    valid = replace(obs,quote="Dung tích: 83 ml.")
    run = core_db.run()
    assert publish.gate(policy.decide("volume",[valid],{},[],[]),run,{"id":core_db.case_id})
    invalid = replace(obs,quote="83 ml. words.")
    assert not publish.gate(policy.decide("volume",[invalid],{},[],[]),run,{"id":core_db.case_id})
    assert len(core_db.rows("SELECT * FROM field_results")) == 1


def test_unchanged_decision_confirms_without_new_version(core_db: CoreDB) -> None:
    decision = policy.decide("volume",[core_db.source()],{},[],[])
    assert publish.gate(decision,core_db.run(),{"id":core_db.case_id})
    before = core_db.rows("SELECT * FROM field_results")[0]
    second_run = core_db.run()
    assert publish.gate(decision,second_run,{"id":core_db.case_id})
    after = core_db.rows("SELECT * FROM field_results")
    assert len(after) == 1
    assert after[0]["id"] == before["id"]
    assert after[0]["result_version"] == 1
    assert after[0]["confirmed_run_id"] == second_run["id"]


def test_missing_claim_opens_one_request_and_readable_claim_closes_it(core_db: CoreDB) -> None:
    missing = policy.decide("volume",[],{},[],[])
    for _ in range(2):
        assert publish.gate(missing,core_db.run(),{"id":core_db.case_id})
    assert len(core_db.rows("SELECT * FROM gaps WHERE status='OPEN'")) == 1
    assert len(core_db.rows("SELECT * FROM evidence_requests WHERE status='OPEN'")) == 1
    found = policy.decide("volume",[core_db.source()],{},[],[])
    assert publish.gate(found,core_db.run(),{"id":core_db.case_id})
    assert not core_db.rows("SELECT * FROM gaps WHERE status='OPEN'")
    assert not core_db.rows("SELECT * FROM evidence_requests WHERE status='OPEN'")
    assert len(core_db.rows("SELECT * FROM field_results")) == 2
