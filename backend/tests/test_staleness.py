"""S2 admission and stable evidence identity on arbitrary source versions."""
from pathlib import Path
from dataclasses import replace
import pytest
from app import config, db, seed, worker
from app.events.admit import admit
from app.models import Role
from app.llm.client import LLMError
from app.pipeline import policy, publish
from p1_helpers import CoreDB, core_db
from test_run import extraction


def test_revoke_admission_is_model_free_and_first_trace_is_stale(core_db: CoreDB) -> None:
    obs = core_db.source()
    finding = policy.decide("volume",[obs],{},[],[])
    assert publish.gate(finding,core_db.run(),{"id":core_db.case_id})
    before_runs = len(core_db.rows("SELECT * FROM runs"))
    event = core_db.event("SOURCE_REVOKED",resource_kind="SOURCE",resource_id=obs.source_id)
    result = admit(event,role=Role.OPERATOR,actor_id="operator")
    assert result.stale_fields == ["volume"]
    assert len(core_db.rows("SELECT * FROM runs")) == before_runs
    assert core_db.rows("SELECT freshness FROM field_results")[0]["freshness"] == "STALE"
    worker.execute_job(result.job_id,extractor=extraction)
    run = core_db.rows("SELECT run_id FROM jobs")[0]["run_id"]
    first = core_db.rows("SELECT * FROM trace_steps WHERE run_id=? ORDER BY seq",(run,))[0]
    assert first["step"] == "stale:mark"
    assert db.loads(first["detail"])["model_calls"] == 0


@pytest.mark.parametrize("limit", ["0","1"])
def test_budget_zero_results_still_partial(core_db: CoreDB, monkeypatch: pytest.MonkeyPatch, limit: str) -> None:
    core_db.source()
    monkeypatch.setenv("RUN_MAX_MODEL_CALLS",limit)
    config.reload_settings()
    def exhausted(sv_id, ctx):
        for _ in range(int(limit)+1):
            ctx.budget.take_model_call("boundary")
        return extraction(sv_id,ctx)
    result = admit(core_db.event(),role=Role.OPERATOR,actor_id="operator")
    worker.execute_job(result.job_id,extractor=exhausted)
    assert core_db.rows("SELECT status FROM runs")[0]["status"] == "PARTIAL"


def test_reset_preserves_exact_source_and_passage_ids(client) -> None:
    from app.api.read import rows
    before = rows("SELECT id,source_version_id,locator,text FROM passages ORDER BY id")
    seed.reset()
    assert rows("SELECT id,source_version_id,locator,text FROM passages ORDER BY id") == before


@pytest.mark.parametrize("volume", [97,121])
def test_admission_rejects_old_snapshot_without_revision_or_job(core_db: CoreDB, tmp_path: Path,
                                                              monkeypatch: pytest.MonkeyPatch, volume: int) -> None:
    core_db.source("changing-source",version=2)
    monkeypatch.setenv("FIXTURES_DIR",str(tmp_path))
    config.reload_settings()
    folder = tmp_path/"synthetic"
    folder.mkdir()
    snapshot = {"source_id":"changing-source","product_id":core_db.product_id,"kind":"PACKAGING_IMAGE",
                "version":1,"passages":[{"locator":"p:1","text":f"Volume {volume} ml"}]}
    (folder/"older.json").write_text(db.dumps(snapshot),encoding="utf-8")
    event = core_db.event("SOURCE_CHANGED",resource_kind="SOURCE",resource_id="changing-source")
    event.payload["snapshot"] = "synthetic/older.json"
    before = core_db.rows("SELECT * FROM source_versions")
    result = admit(event,role=Role.OPERATOR,actor_id="operator")
    assert result.outcome == "NOOP" and result.job_id is None
    assert core_db.rows("SELECT * FROM source_versions") == before
    assert core_db.rows("SELECT revision FROM cases")[0]["revision"] == 0


def test_revoke_model_error_preserves_unaffected_result(core_db: CoreDB) -> None:
    volume = core_db.source("label")
    company = replace(core_db.source("notice",kind="NOTIFICATION_DOC",text="Company: Delta Lab."),
                      field_key="responsible_company",normalized={"value":"Delta Lab"})
    for obs in (volume,company):
        assert publish.gate(policy.decide(obs.field_key,[obs],{},[],[]),core_db.run(),{"id":core_db.case_id})
    before = core_db.rows("SELECT * FROM field_results WHERE field_key='volume'")[0]
    admitted = admit(core_db.event("SOURCE_REVOKED",resource_kind="SOURCE",resource_id="notice"),role=Role.OPERATOR,actor_id="operator")
    assert admitted.stale_fields == ["responsible_company"]

    def failed(sv_id, ctx):
        raise LLMError("API_ERROR")

    worker.execute_job(admitted.job_id,extractor=failed)
    after = core_db.rows("SELECT * FROM field_results WHERE field_key='volume' AND superseded_by IS NULL")[0]
    for key in ("id","result_version","verdict","citations_json","explain_json","freshness"):
        assert after[key] == before[key]
    changed = core_db.rows("SELECT * FROM field_results WHERE field_key='responsible_company' AND superseded_by IS NULL")[0]
    assert changed["verdict"] == "INSUFFICIENT" and db.loads(changed["citations_json"]) == []
    assert core_db.rows("SELECT missing_kind FROM gaps WHERE status='OPEN'") == [{"missing_kind":"MODEL_ERROR"}]
    assert core_db.rows("SELECT status FROM runs WHERE id=(SELECT run_id FROM jobs)")[0]["status"] == "PARTIAL"


def test_revoke_unused_source_finishes_without_false_failure(core_db: CoreDB) -> None:
    source = core_db.source("unused")
    admitted = admit(core_db.event("SOURCE_REVOKED",resource_kind="SOURCE",resource_id=source.source_id),role=Role.OPERATOR,actor_id="operator")
    assert admitted.stale_fields == []
    worker.execute_job(admitted.job_id,extractor=extraction)
    assert core_db.rows("SELECT status,stop_reason FROM runs") == [{"status":"COMPLETED","stop_reason":None}]


def test_unaffected_conflict_remains_reviewable_after_revoke(core_db: CoreDB) -> None:
    from app.api.cases import review_queue
    from app.api.dependencies import RequestActor
    first = core_db.source("first")
    second = replace(core_db.source("second",kind="BRAND_PAGE",text="Volume: 91 ml."),normalized={"value":91,"unit":"ml"})
    core_db.source("unused-notice",kind="NOTIFICATION_DOC")
    decision = policy.decide("volume",[first,second],{},[],[])
    assert decision.review_state == "NEEDS_REVIEW"
    assert publish.gate(decision,core_db.run(),{"id":core_db.case_id})
    before = core_db.rows("SELECT * FROM field_results")[0]
    admitted = admit(core_db.event("SOURCE_REVOKED",resource_kind="SOURCE",resource_id="unused-notice"),role=Role.OPERATOR,actor_id="operator")
    worker.execute_job(admitted.job_id,extractor=extraction)
    after = core_db.rows("SELECT * FROM field_results WHERE superseded_by IS NULL")[0]
    assert after["id"] == before["id"] and after["result_version"] == before["result_version"]
    queue = review_queue(RequestActor(Role.REVIEWER,"reviewer"))
    assert len(queue) == 1 and queue[0].result_id == before["id"] and queue[0].case_revision == 1
    assert publish.review(core_db.case_id,str(before["id"]),1,"APPROVE","Checked retained evidence",None,"reviewer")


def test_unaffected_claim_review_survives_unrelated_revoke(core_db: CoreDB) -> None:
    claim = replace(core_db.source("claim-source"),field_key="claim:treatment:skin",normalized={"value":"treatment"})
    core_db.source("unused-notice",kind="NOTIFICATION_DOC")
    assert publish.gate(policy.decide(claim.field_key,[claim],{},[],[]),core_db.run(),{"id":core_db.case_id})
    before = core_db.rows("SELECT * FROM field_results")[0]
    admitted = admit(core_db.event("SOURCE_REVOKED",resource_kind="SOURCE",resource_id="unused-notice"),role=Role.OPERATOR,actor_id="operator")
    worker.execute_job(admitted.job_id,extractor=extraction)
    assert core_db.rows("SELECT result_id FROM review_tasks WHERE status='OPEN'") == [{"result_id":before["id"]}]
    assert publish.review(core_db.case_id,str(before["id"]),1,"APPROVE","Retained claim reviewed",None,"reviewer")


@pytest.mark.parametrize("action", ["APPROVE","OVERRIDE"])
def test_unrelated_revoke_expires_prior_revision_approval(core_db: CoreDB, action: str) -> None:
    obs = core_db.source("label")
    core_db.source("unused-notice",kind="NOTIFICATION_DOC")
    finding = policy.decide("volume",[obs],{},[],[])
    assert publish.gate(finding,core_db.run(),{"id":core_db.case_id})
    identity = core_db.rows("SELECT id FROM field_results")[0]["id"]
    override = {"verdict":"SINGLE_SOURCE","citations":[c.model_dump(mode="json") for c in finding.citations],
                "public_text":"Stated by the cited source."} if action == "OVERRIDE" else None
    review_id = publish.review(core_db.case_id,str(identity),0,action,"Checked source",override,"reviewer")
    reviewed = core_db.rows("SELECT * FROM field_results WHERE superseded_by IS NULL")[0]
    assert reviewed["review_state"] == "REVIEWED"
    admitted = admit(core_db.event("SOURCE_REVOKED",resource_kind="SOURCE",resource_id="unused-notice"),role=Role.OPERATOR,actor_id="operator")
    worker.execute_job(admitted.job_id,extractor=extraction)
    current = core_db.rows("SELECT * FROM field_results WHERE superseded_by IS NULL")[0]
    assert current["review_state"] == "NEEDS_REVIEW" and current["case_revision"] == 1
    assert current["result_version"] == reviewed["result_version"]+1
    assert current["citations_json"] == reviewed["citations_json"]
    assert core_db.rows("SELECT review_state FROM field_results WHERE id=?",(reviewed["id"],))[0]["review_state"] == "REVIEWED"
    assert core_db.rows("SELECT result_id FROM review_tasks WHERE status='OPEN'") == [{"result_id":current["id"]}]
    review = core_db.rows("SELECT * FROM reviews WHERE id=?",(review_id,))[0]
    assert policy.review_freshness(review["case_revision"],1) == "SUPERSEDED"
