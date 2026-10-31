"""Optional extraction retains claims while the run honors its sticky budget stop."""
import pytest

from app import config, db, store, worker
from app.budget import BudgetExceeded
from app.context import RunContext
from app.events.admit import admit
from app.models import Readability, Role
from app.pipeline.extract import Claim, Extraction
from p1_helpers import CoreDB, core_db


@pytest.mark.parametrize("source_count", [1, 2])
@pytest.mark.parametrize("reason", ["MODEL_CALL_LIMIT", "RUN_DEADLINE"])
def test_retained_extraction_with_budget_stop_is_partial(core_db: CoreDB,
        monkeypatch: pytest.MonkeyPatch, source_count: int, reason: str) -> None:
    first = core_db.source("first")
    if source_count == 2:
        core_db.source("later")
    monkeypatch.setenv("RUN_MAX_MODEL_CALLS", "1")
    config.reload_settings()
    calls: list[str] = []

    def retained(sv_id: str, ctx: RunContext) -> Extraction:
        calls.append(sv_id)
        ctx.budget.take_model_call("initial-extraction")
        passage = store.passages(sv_id)[0]
        claim = Claim("retained-claim", sv_id, passage["id"], "volume", "83 ml",
                      {"value":83,"unit":"ml"}, passage["text"], Readability.READABLE,
                      "FALLBACK", "unit-retained", "code")
        try:
            if reason == "RUN_DEADLINE":
                ctx.budget.expire()
            else:
                ctx.budget.take_model_call("optional-retry")
        except BudgetExceeded as failure:
            assert failure.reason == reason
        return Extraction([claim], False, "FALLBACK", False)

    admission = admit(core_db.event(), role=Role.OPERATOR, actor_id="operator")
    worker.execute_job(admission.job_id, extractor=retained)
    run = core_db.rows("SELECT status,stop_reason FROM runs")[0]
    assert run == {"status":"PARTIAL", "stop_reason":reason}
    assert calls == [first.source_version_id]
    findings = core_db.rows("SELECT field_key,verdict,citations_json FROM field_results")
    assert len(findings) == 1 and findings[0]["field_key"] == "volume"
    assert findings[0]["verdict"] == "SINGLE_SOURCE"
    assert db.loads(findings[0]["citations_json"])[0]["passage_id"] == first.passage_id
    assert not core_db.rows("SELECT id FROM evidence_requests")
