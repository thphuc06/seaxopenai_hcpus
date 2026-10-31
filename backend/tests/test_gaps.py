"""Real registry persistence/policy/publication with an offline connector seam."""
from dataclasses import replace
import pytest
from app import db, store
from app.budget import Budget, BudgetExceeded
from app.connectors import registry
from app.context import RunContext
from app.pipeline import gaps, normalize, policy, publish
from app.trace import TraceWriter
from p1_helpers import CoreDB, core_db


def context(core: CoreDB, budget: Budget | None = None) -> RunContext:
    run = core.run()
    return RunContext(str(run["id"]), core.case_id, "unit-tenant", 0,
        {"id":core.product_id,"case_id":core.case_id,"tenant_id":"unit-tenant","variant":"83ml","market":"VN"},
        "fallback", budget or Budget(), TraceWriter(str(run["id"])))


def observations(core: CoreDB, number: str, company: str):
    base = core.source(kind="LISTING", text=f"Number {number}; company {company}.")
    return [replace(base, field_key=field, normalized=normalize.normalize(field, raw))
            for field, raw in (("notification_number", number), ("responsible_company", company))]


@pytest.mark.parametrize("number,company", [("VN-835", "Northshore LLC"), ("AB-297", "Orchard Ltd")])
def test_registry_closes_identifiers_with_real_citations_and_idempotency(core_db: CoreDB, monkeypatch: pytest.MonkeyPatch, number: str, company: str) -> None:
    ctx = context(core_db)
    obs = observations(core_db, number, company)
    calls = []
    def lookup(value: str):
        calls.append(value)
        return registry.RegistryRecord(product_name="Sample", holder=company, status="ACTIVE", issued="2026-10-31")
    monkeypatch.setattr(registry, "lookup", lookup)
    decisions = [policy.decide(field, obs, ctx.product, [], []) for field in ("notification_number", "responsible_company")]
    result = gaps.close_gaps(ctx, decisions, obs)
    assert len(result.new_sv_ids) == len(calls) == 1
    source = next(s for s in store.current_sources(ctx.case_id) if s["source_version_id"] == result.new_sv_ids[0])
    obs += gaps.registry_observations(source, ctx)
    for field in ("notification_number", "responsible_company"):
        decision = policy.decide(field, obs, ctx.product, [], [])
        assert decision.verdict == "CONSISTENT" and "MOCK" in decision.public_text
        assert publish.gate(decision, {"id":ctx.run_id}, {"id":ctx.case_id})
    repeated = gaps.close_gaps(ctx, decisions, obs)
    assert repeated.new_sv_ids == [] and repeated.stops == ["ALREADY_CHECKED"]
    assert len(calls) == 1 and ctx.budget.tool_calls == 3


@pytest.mark.parametrize("status", ["REVOKED", "ABSENT"])
def test_registry_never_closes_missing_or_revoked_record(core_db: CoreDB, monkeypatch: pytest.MonkeyPatch, status: str) -> None:
    ctx = context(core_db)
    obs = observations(core_db, "XY-817", "Example Company")
    monkeypatch.setattr(registry, "lookup", lambda number: None if status == "ABSENT" else registry.RegistryRecord(product_name="Sample", holder="Example Company", status=status, issued="2026-10-31"))
    decisions = [policy.decide("notification_number", obs, ctx.product, [], [])]
    result = gaps.close_gaps(ctx, decisions, obs)
    assert result.stops == ["NOT_FOUND" if status == "ABSENT" else "REVOKED_IN_REGISTRY"]
    for source in store.current_sources(ctx.case_id):
        if source["kind"] == "REGISTRY_RECORD":
            obs += gaps.registry_observations(source, ctx)
    assert policy.decide("notification_number", obs, ctx.product, [], []).verdict == "INSUFFICIENT"


def test_no_key_and_exhausted_budget_do_not_create_registry_evidence(core_db: CoreDB) -> None:
    ctx = context(core_db)
    obs = observations(core_db, "ZZ-91", "Example Company")
    decisions = [policy.decide("notification_number", obs, ctx.product, [], [])]
    assert gaps.close_gaps(ctx, decisions, []).stops == ["NO_JOIN_KEY"]
    exhausted = context(core_db, Budget(max_tool_calls=0))
    before = core_db.dump()
    with pytest.raises(BudgetExceeded):
        gaps.close_gaps(exhausted, decisions, obs)
    assert core_db.dump() == before


def test_missing_registry_key_is_remembered_across_runs(core_db: CoreDB, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = context(core_db)
    obs = observations(core_db, "MISSING-82", "Example Company")
    decisions = [policy.decide("notification_number", obs, ctx.product, [], [])]
    calls = []
    def missing(number: str):
        calls.append(number)
        return None
    monkeypatch.setattr(registry, "lookup", missing)
    assert gaps.close_gaps(ctx, decisions, obs).stops == ["NOT_FOUND"]
    assert gaps.close_gaps(context(core_db), decisions, obs).stops == ["ALREADY_CHECKED"]
    assert len(calls) == 1


def test_partial_lookup_retains_first_verified_record(core_db: CoreDB, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = context(core_db, Budget(max_tool_calls=2))
    obs = observations(core_db, "AA-18", "Example Company")
    second = core_db.source(source_id="other-label", text="Number BB-29")
    obs.append(replace(second, field_key="notification_number", normalized=normalize.normalize("notification_number", "BB-29")))
    # Force the optional registry path with an existing missing-document decision;
    # the contradictory numbers remain policy inputs, never rewritten to agree.
    decisions = [policy.decide("notification_number", obs[:2], ctx.product, [], [])]
    monkeypatch.setattr(registry, "lookup", lambda number: registry.RegistryRecord(product_name="Sample", holder="Example Company", status="ACTIVE", issued="2026-10-31"))
    outcome = gaps.close_gaps(ctx, decisions, obs)
    assert len(outcome.new_sv_ids) == 1 and outcome.stops == ["TOOL_CALL_LIMIT"]
    assert ctx.budget.stop_reason == "TOOL_CALL_LIMIT"
    assert len([s for s in store.current_sources(ctx.case_id) if s["kind"] == "REGISTRY_RECORD"]) == 1


@pytest.mark.parametrize("failure", [ValueError("invalid record"), FileNotFoundError("missing registry")])
def test_registry_errors_are_explicit_stops(core_db: CoreDB, monkeypatch: pytest.MonkeyPatch, failure: Exception) -> None:
    ctx = context(core_db)
    obs = observations(core_db, "AA-18", "Example Company")
    decisions = [policy.decide("notification_number", obs, ctx.product, [], [])]
    def broken(number: str):
        raise failure
    monkeypatch.setattr(registry, "lookup", broken)
    assert gaps.close_gaps(ctx, decisions, obs).stops == ["REGISTRY_ERROR"]
    assert not core_db.rows("SELECT id FROM sources WHERE kind='REGISTRY_RECORD'")
    assert len(core_db.rows("SELECT id FROM trace_steps WHERE step='gap:stop' AND run_id=?", (ctx.run_id,))) == 1


def test_registry_metadata_cannot_override_passage_value_or_scope(core_db: CoreDB) -> None:
    ctx = context(core_db)
    source = core_db.source(kind="REGISTRY_RECORD", visibility="PRIVATE", text="MOCK registry notification number: REAL-82")
    with db.transaction() as connection:
        connection.execute("UPDATE passages SET section='notification_number' WHERE id=?", (source.passage_id,))
        connection.execute("UPDATE source_versions SET scope_json=? WHERE id=?", (db.dumps({"variant":"166ml","registry_number":"INVENTED"}), source.source_version_id))
    obs = gaps.registry_observations(store.current_sources(ctx.case_id)[0], ctx)
    assert obs[0].normalized == normalize.normalize("notification_number", "REAL-82")
    assert obs[0].scope_match == "MISMATCH" and obs[0].visibility == "PRIVATE"
