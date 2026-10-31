from collections.abc import Callable
import pytest
from app import config, db, store, worker
from app.context import RunContext
from app.events.admit import admit
from app.llm.client import LLMError, ErrorCode
from app.models import Readability, Role
from app.pipeline.extract import Claim, Extraction
from p1_helpers import CoreDB, core_db

pytestmark = pytest.mark.phase(1)


def extraction(sv_id: str, ctx: RunContext) -> Extraction:
    passage = store.passages(sv_id)[0]
    claim = Claim("unit-claim-"+sv_id,sv_id,passage["id"],"volume","83 ml",{"value":83,"unit":"ml"},
                  passage["text"],Readability.READABLE,"FALLBACK","unit-prompt","code")
    return Extraction([claim],False,"FALLBACK",False)


def submit(core_db: CoreDB, extractor: Callable[[str,RunContext],Extraction] = extraction) -> str:
    result = admit(core_db.event(),role=Role.OPERATOR,actor_id="operator")
    assert result.job_id
    worker.execute_job(result.job_id,extractor=extractor)
    return result.job_id


def test_pipeline_pins_revision_publishes_cited_results_and_waits_for_missing_fields(core_db: CoreDB) -> None:
    source = core_db.source()
    submit(core_db)
    results = core_db.rows("SELECT * FROM field_results")
    assert len(results) == 5
    assert {r["case_revision"] for r in results} == {1}
    volume = next(r for r in results if r["field_key"] == "volume")
    assert volume["verdict"] == "SINGLE_SOURCE"
    assert db.loads(volume["citations_json"])[0]["passage_id"] == source.passage_id
    run = core_db.rows("SELECT * FROM runs")[0]
    assert run["status"] == "WAITING_EVIDENCE"
    assert db.loads(run["usage_json"])["model_calls"]["used"] == 0
    assert run["model"] and run["prompt_version"] and run["policy_version"]
    assert len(core_db.rows("SELECT * FROM evidence_requests WHERE status='OPEN'")) == 4
    steps = {row["step"] for row in core_db.rows("SELECT step FROM trace_steps")}
    assert {"pin_revision","scope_check","extract","policy:volume","publish","run:stop"} <= steps


def test_budget_exhaustion_keeps_code_verified_fields_and_records_partial(core_db: CoreDB, monkeypatch: pytest.MonkeyPatch) -> None:
    core_db.source("first")
    core_db.source("second",kind="BRAND_PAGE")
    monkeypatch.setenv("RUN_MAX_MODEL_CALLS","1")
    config.reload_settings()

    def capped(sv_id: str, ctx: RunContext) -> Extraction:
        ctx.budget.take_model_call("injected-extraction")
        return extraction(sv_id,ctx)

    submit(core_db,capped)
    run = core_db.rows("SELECT * FROM runs")[0]
    assert run["status"] == "PARTIAL" and run["stop_reason"]
    assert db.loads(run["usage_json"])["model_calls"]["used"] == 1
    volume = core_db.rows("SELECT * FROM field_results WHERE field_key='volume'")[0]
    assert volume["verdict"] == "SINGLE_SOURCE"
    assert len(db.loads(volume["citations_json"])) == 1


def test_revision_advanced_during_extraction_blocks_old_run_and_drains_latest_job(core_db: CoreDB) -> None:
    core_db.source()
    advanced = False

    def interleaving(sv_id: str, ctx: RunContext) -> Extraction:
        nonlocal advanced
        if not advanced:
            advanced = True
            admit(core_db.event(),role=Role.OPERATOR,actor_id="operator")
        return extraction(sv_id,ctx)

    submit(core_db,interleaving)
    runs = core_db.rows("SELECT * FROM runs ORDER BY case_revision")
    assert len(runs) == 2
    assert runs[0]["case_revision"] == 1 and runs[0]["status"] == "FAILED"
    assert {r["case_revision"] for r in core_db.rows("SELECT * FROM field_results")} == {2}
    blocked = core_db.rows("SELECT detail FROM trace_steps WHERE run_id=? AND step='publish:blocked'", (runs[0]["id"],))
    assert blocked and all(db.loads(r["detail"])["reason"] == "SUPERSEDED_RUN" for r in blocked)
    assert {j["status"] for j in core_db.rows("SELECT * FROM jobs")} == {"FINISHED"}


def test_repeated_worker_dispatch_does_not_rerun_finished_job(core_db: CoreDB) -> None:
    core_db.source()
    job_id = submit(core_db)
    before = core_db.dump()
    worker.execute_job(job_id,extractor=extraction)
    assert core_db.dump() == before


def test_extractor_invalid_quote_never_reaches_published_citations(core_db: CoreDB) -> None:
    core_db.source()

    def invalid(sv_id: str, ctx: RunContext) -> Extraction:
        result = extraction(sv_id,ctx)
        result.claims[0].quote = "Unstored words"
        return result

    submit(core_db,invalid)
    assert all(row["verdict"] == "INSUFFICIENT" for row in core_db.rows("SELECT * FROM field_results"))
    assert any("INVALID_LOCATOR" in row["detail"] for row in core_db.rows("SELECT detail FROM trace_steps"))


@pytest.mark.parametrize("code", ["REPLAY_MISS","REFUSAL","INCOMPLETE","API_ERROR"])
def test_typed_model_errors_finish_run_with_sanitized_diagnostics(core_db: CoreDB, code: ErrorCode) -> None:
    core_db.source()

    def failed(sv_id: str, ctx: RunContext) -> Extraction:
        raise LLMError(code,"private external error detail")

    submit(core_db,failed)
    run = core_db.rows("SELECT * FROM runs")[0]
    assert run["status"] == "FAILED" and run["stop_reason"] == code
    assert run["error"] == "LLMError"
    assert not core_db.rows("SELECT * FROM field_results")
    assert "private external error detail" not in str(core_db.dump())
    assert core_db.rows("SELECT status FROM jobs")[0]["status"] == "FINISHED"


def test_model_error_after_one_source_keeps_only_assessed_fields(core_db: CoreDB) -> None:
    core_db.source("first")
    core_db.source("second",kind="BRAND_PAGE")
    calls = 0

    def interrupted(sv_id: str, ctx: RunContext) -> Extraction:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise LLMError("REPLAY_MISS")
        return extraction(sv_id,ctx)

    submit(core_db,interrupted)
    run = core_db.rows("SELECT * FROM runs")[0]
    assert run["status"] == "PARTIAL" and run["stop_reason"] == "REPLAY_MISS"
    assert {r["field_key"] for r in core_db.rows("SELECT * FROM field_results")} == {"volume"}
    assert not core_db.rows("SELECT * FROM evidence_requests")
