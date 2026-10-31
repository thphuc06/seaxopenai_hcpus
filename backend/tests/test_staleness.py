"""S2 admission and stable evidence identity on arbitrary source versions."""
from pathlib import Path
import pytest
from app import config, db, seed, worker
from app.events.admit import admit
from app.models import Role
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
