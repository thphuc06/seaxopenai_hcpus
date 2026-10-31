"""S3 orchestration with explicit external connector/scope seams, real policy/storage."""
import pytest
from app import config, db, store, worker, chain
from app.agent import scope_resolution
from app.connectors import registry
from app.events.admit import admit
from app.models import Readability, Role, ScopeMatch
from app.pipeline.extract import Claim, Extraction
from app.pipeline import normalize
from app.context import RunContext
from p1_helpers import CoreDB, core_db


def identifier_extractor(sv_id: str, ctx: RunContext) -> Extraction:
    p = store.passages(sv_id)[0]
    number = str(p["text"]).split(";")[0]
    values = [("notification_number", number), ("responsible_company", "Example Company")]
    claims = [Claim("claim-"+sv_id+field, sv_id, str(p["id"]), field, raw, normalize.normalize(field,raw), str(p["text"]), Readability.READABLE, "FALLBACK", "test", "code") for field,raw in values]
    return Extraction(claims, False, "FALLBACK", False)


def execute(core: CoreDB, extractor) -> None:
    admitted = admit(core.event(), role=Role.OPERATOR, actor_id="operator")
    worker.execute_job(admitted.job_id, extractor=extractor)


def test_partial_gap_run_publishes_first_lookup_evidence(core_db: CoreDB, monkeypatch: pytest.MonkeyPatch) -> None:
    core_db.source("first", kind="LISTING", text="AA-1; Example Company")
    core_db.source("second", text="BB-2; Example Company")
    monkeypatch.setenv("AGENT_MAX_TOOL_CALLS", "2")
    config.reload_settings()
    monkeypatch.setattr(registry,"lookup", lambda key: registry.RegistryRecord(product_name="Sample",holder="Example Company",status="ACTIVE",issued="2026-10-31"))
    execute(core_db, identifier_extractor)
    run = core_db.rows("SELECT * FROM runs")[0]
    assert run["status"] == "PARTIAL" and run["stop_reason"] == "TOOL_CALL_LIMIT"
    company = core_db.rows("SELECT * FROM field_results WHERE field_key='responsible_company'")[0]
    assert company["verdict"] == "CONSISTENT"
    assert any(c["source_kind"] == "REGISTRY_RECORD" for c in db.loads(company["citations_json"]))
    assert chain.verify(core_db.case_id).valid


@pytest.mark.parametrize("failure", [ValueError("bad shape"), FileNotFoundError("unavailable")])
def test_connector_failure_preserves_pass_one_results(core_db: CoreDB, monkeypatch: pytest.MonkeyPatch, failure: Exception) -> None:
    core_db.source("listing", kind="LISTING", text="AA-1; Example Company")
    def broken(number: str):
        raise failure
    monkeypatch.setattr(registry, "lookup", broken)
    execute(core_db, identifier_extractor)
    run = core_db.rows("SELECT * FROM runs")[0]
    assert run["status"] == "PARTIAL" and run["stop_reason"] == "REGISTRY_ERROR"
    number = core_db.rows("SELECT * FROM field_results WHERE field_key='notification_number'")[0]
    assert number["verdict"] == "INSUFFICIENT" and db.loads(number["citations_json"])
    assert chain.verify(core_db.case_id).valid


def test_scope_seam_effect_is_decided_by_real_policy(core_db: CoreDB, monkeypatch: pytest.MonkeyPatch) -> None:
    core_db.source("listing",kind="LISTING",text="Skin: oily.")
    reference = core_db.source("catalogue",kind="BRAND_PAGE",text="83 ml and 166 ml. Skin: oily.")
    with db.transaction() as connection:
        connection.execute("UPDATE source_versions SET scope_json='{}' WHERE id=?", (reference.source_version_id,))
    def extract(sv_id: str, ctx: RunContext) -> Extraction:
        p = store.passages(sv_id)[0]
        return Extraction([Claim("claim-"+sv_id,sv_id,str(p["id"]),"skin_type","oily",{"value":["OILY"]},str(p["text"]),Readability.READABLE,"FALLBACK","test","code")],False,"FALLBACK",False)
    def resolve(ctx, observations, fields):
        assert "skin_type" in fields
        ctx.budget.take_tool("test-scope-seam")
        with db.transaction() as connection:
            connection.execute("INSERT INTO passage_scopes VALUES(?,?,?,?,?,?,?)",(reference.source_version_id,reference.passage_id,"MATCH","External validated placement","CODE",ctx.run_id,db.now_iso()))
        placed = scope_resolution.PassageScope(reference.passage_id,reference.source_version_id,ScopeMatch.MATCH,"CODE",None,"Test seam")
        return scope_resolution.ScopeOutcome([placed],True,None,"Test seam")
    monkeypatch.setattr(scope_resolution,"resolve_all",resolve)
    execute(core_db,extract)
    skin = core_db.rows("SELECT * FROM field_results WHERE field_key='skin_type'")[0]
    assert skin["verdict"] == "CONSISTENT"
    effects = core_db.rows("SELECT detail FROM trace_steps WHERE step='agent:effect'")
    assert any(db.loads(e["detail"])["after"] == "CONSISTENT" for e in effects)


@pytest.mark.parametrize("text", ["Bottle 83 ml. Gift with purchase of a 97 ml bottle.", "Free gift with purchase of an 83 ml bottle"])
def test_noop_scope_seam_preserves_ambiguous_volume(core_db: CoreDB, monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    core_db.source("listing", kind="LISTING", text=text)
    monkeypatch.setattr(scope_resolution,"resolve_all",lambda ctx, observations, fields: scope_resolution.ScopeOutcome([],False,None,"No placement"))
    admitted = admit(core_db.event(),role=Role.OPERATOR,actor_id="operator")
    worker.execute_job(admitted.job_id)
    assert core_db.rows("SELECT verdict FROM field_results WHERE field_key='volume'")[0]["verdict"] == "UNCERTAIN"


def test_new_source_without_snapshot_cannot_schedule(core_db: CoreDB) -> None:
    result = admit(core_db.event("SOURCE_CHANGED",resource_kind="SOURCE",resource_id="missing-source"),role=Role.OPERATOR,actor_id="operator")
    assert result.outcome == "REJECTED" and result.job_id is None
    assert core_db.rows("SELECT revision FROM cases")[0]["revision"] == 0
