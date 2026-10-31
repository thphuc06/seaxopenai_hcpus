import pytest
from app.events.admit import admit
from app.models import Role, EventOutcome
from app.pipeline import policy, publish
from p1_helpers import CoreDB, core_db

pytestmark = pytest.mark.phase(1)


@pytest.mark.parametrize("changed", [["price"],["stock","promo"],["price","stock","promo"],[]])
def test_noop_only_appends_event(core_db: CoreDB, changed: list[str]) -> None:
    before = {table:core_db.rows(f"SELECT * FROM {table}") for table in ("cases","jobs","runs","field_results","gaps","claims")}
    event = core_db.event("LISTING_CHANGED",resource_kind="LISTING",resource_id="unit-listing",changed_fields=changed)
    result = admit(event,role=Role.OPERATOR,actor_id="operator")
    assert result.outcome == EventOutcome.NOOP and result.job_id is None
    assert len(core_db.rows("SELECT * FROM events")) == 1
    assert before == {table:core_db.rows(f"SELECT * FROM {table}") for table in before}


def test_duplicate_has_zero_database_side_effects(core_db: CoreDB) -> None:
    event = core_db.event()
    admit(event,role=Role.OPERATOR,actor_id="operator")
    before = core_db.dump()
    result = admit(event,role=Role.OPERATOR,actor_id="operator")
    assert result.outcome == EventOutcome.DUPLICATE
    assert before == core_db.dump()


@pytest.mark.parametrize("role,producer", [(Role.BUYER,"publisher-panel"),(Role.OPERATOR,"unknown-producer"),(Role.SELLER,"publisher-panel")])
def test_rejected_identity_cannot_schedule(core_db: CoreDB, role: Role, producer: str) -> None:
    result = admit(core_db.event(producer=producer),role=role,actor_id="caller")
    assert result.outcome == EventOutcome.REJECTED
    assert not core_db.rows("SELECT * FROM jobs")
    assert core_db.rows("SELECT revision FROM cases")[0]["revision"] == 0


def test_queued_events_coalesce_to_latest_revision(core_db: CoreDB) -> None:
    first = admit(core_db.event(),role=Role.OPERATOR,actor_id="operator")
    second = admit(core_db.event(),role=Role.SYSTEM,actor_id="system")
    assert first.job_id == second.job_id
    jobs = core_db.rows("SELECT * FROM jobs")
    assert len(jobs) == 1 and jobs[0]["target_revision"] == 2
    assert core_db.rows("SELECT revision FROM cases")[0]["revision"] == 2


def test_source_event_stales_only_dependent_fields(core_db: CoreDB) -> None:
    label = core_db.source()
    other = core_db.source("another-label",text="Skin: dry.")
    from dataclasses import replace
    skin = replace(other,field_key="skin_type",normalized={"value":["DRY"]})
    run = core_db.run()
    for field,obs in (("volume",label),("skin_type",skin)):
        assert publish.gate(policy.decide(field,[obs],{},[],[]),run,{"id":core_db.case_id})
    event = core_db.event("SOURCE_CHANGED",resource_kind="SOURCE",resource_id=label.source_id)
    result = admit(event,role=Role.OPERATOR,actor_id="operator")
    assert result.stale_fields == ["volume"]
    freshness = {row["field_key"]:row["freshness"] for row in core_db.rows("SELECT * FROM field_results")}
    assert freshness == {"volume":"STALE","skin_type":"CURRENT"}


def test_payload_cannot_rebind_resource_to_another_case(core_db: CoreDB) -> None:
    event = core_db.event().model_copy(update={"payload":{"case_id":"another-case"}})
    result = admit(event,role=Role.OPERATOR,actor_id="operator")
    assert result.outcome == EventOutcome.REJECTED
    assert not core_db.rows("SELECT * FROM jobs")
