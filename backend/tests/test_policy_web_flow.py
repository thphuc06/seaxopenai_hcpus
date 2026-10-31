"""P1 web lifecycle uses the existing P2 discover seam, without a provider."""
from collections.abc import Callable

from fastapi.testclient import TestClient
import pytest

from app import config, db, store, worker
from app.context import RunContext
from app.events.admit import admit
from app.main import create_app
from app.models import Role
from app.pipeline import web_sources
from p1_helpers import CoreDB, core_db


def headers(role: str = "OPERATOR") -> dict[str, str]:
    return {"X-Demo-Role": role, "X-Demo-Actor": "web-operator"}


def provider(core: CoreDB, calls: list[RunContext], *, identity: bool = True) -> Callable[[RunContext], web_sources.WebOutcome]:
    def discover(ctx: RunContext) -> web_sources.WebOutcome:
        calls.append(ctx)
        ctx.budget.take_tool("web:search")
        snapshot = {"source_id": "constructed-web-source", "product_id": core.product_id, "kind": "BRAND_PAGE",
            "version": len(calls), "uri": "https://example.test/catalog", "captured_at": db.now_iso(),
            "visibility": "PUBLIC", "family": "constructed-web-family", "scope": {"product": core.product_id,
            "variant": "83ml", "market": "VN", "identity_verified": identity},
            "passages": [{"locator": "paragraph:1", "text": "Volume: 83 ml."}]}
        ref = store.add_source_version(snapshot, case_id=ctx.case_id, origin="SYNTHETIC")
        result = {"url": snapshot["uri"], "domain": "example.test", "class": "BRAND_PAGE", "score": None,
                  "decision": "KEPT", "reason": "Constructed provider response"}
        with db.transaction() as connection:
            connection.execute("INSERT INTO web_searches VALUES(?,?,?,?,?,?,?,?,?)", ("query-" + ctx.run_id,
                ctx.case_id, ctx.run_id, "Constructed product query", "test-provider", "FALLBACK", db.dumps([result]), 0, db.now_iso()))
        return web_sources.WebOutcome([ref.id], [result], None)
    return discover


def enable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEB_SEARCH", "on")
    config.reload_settings()


def test_explicit_web_request_retries_are_readonly_and_audit_is_case_scoped(core_db: CoreDB, monkeypatch: pytest.MonkeyPatch) -> None:
    enable(monkeypatch)
    calls: list[RunContext] = []
    monkeypatch.setattr(web_sources, "discover", provider(core_db, calls))
    core_db.source(kind="LISTING")
    with TestClient(create_app()) as client:
        route = f"/api/cases/{core_db.case_id}/web-search"
        assert client.post(route, headers=headers()).json()["outcome"] == "ADMITTED"
        assert len(calls) == 1 and calls[0].tenant_id == "unit-tenant" and calls[0].case_revision == 1
        assert core_db.rows("SELECT * FROM claims WHERE source_version_id=?", (core_db.rows("SELECT id FROM source_versions WHERE source_id='constructed-web-source'")[0]["id"],))
        before = core_db.dump()
        assert client.post(route, headers=headers()).json()["outcome"] == "DUPLICATE"
        audit = client.get(route, headers=headers("REVIEWER"))
        assert audit.status_code == 200
        value = audit.json()
        assert value["queries"][0]["mode"] == "FALLBACK" and value["queries"][0]["provider"] == "test-provider"
        assert value["snapshots"][0]["identity_verified"] is True
        assert value["snapshots"][0]["passages"][0]["text"] == "Volume: 83 ml."
        for role in ["BUYER", "SELLER", "SYSTEM"]:
            assert client.get(route, headers=headers(role)).status_code == 403
            assert client.post(route, json={"role": "OPERATOR", "actor_id": "spoof"}, headers=headers(role)).status_code == 403
        assert core_db.dump() == before and len(calls) == 1
        event = admit(core_db.event(), role=Role.OPERATOR, actor_id="operator")
        worker.execute_job(event.job_id)
        assert client.post(route, headers=headers()).json()["outcome"] == "ADMITTED"
        assert len(calls) == 2 and calls[-1].case_revision == 3


def test_auto_web_runs_once_per_case_before_extraction(core_db: CoreDB, monkeypatch: pytest.MonkeyPatch) -> None:
    enable(monkeypatch)
    with db.transaction() as connection:
        connection.execute("UPDATE products SET web_json=? WHERE id=?", (db.dumps({"enabled": True}), core_db.product_id))
    core_db.source(kind="LISTING")
    calls: list[RunContext] = []
    monkeypatch.setattr(web_sources, "discover", provider(core_db, calls))
    for _ in range(2):
        result = admit(core_db.event(), role=Role.OPERATOR, actor_id="operator")
        worker.execute_job(result.job_id)
    assert len(calls) == 1
    current = core_db.rows("SELECT * FROM field_results WHERE field_key='volume' AND superseded_by IS NULL")[0]
    assert current["verdict"] == "CONSISTENT"
    assert any(c["source_kind"] == "BRAND_PAGE" for c in db.loads(current["citations_json"]))


@pytest.mark.parametrize("failure", ["empty", "exception", "disabled"])
def test_optional_web_failure_keeps_existing_extractable_evidence(core_db: CoreDB, monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    if failure != "disabled":
        enable(monkeypatch)
    core_db.source(kind="LISTING")
    calls: list[str] = []
    def discover(ctx: RunContext) -> web_sources.WebOutcome:
        calls.append(ctx.run_id)
        if failure == "exception":
            raise RuntimeError("Provider unavailable")
        return web_sources.WebOutcome([], [], None)
    monkeypatch.setattr(web_sources, "discover", discover)
    with TestClient(create_app()) as client:
        assert client.post(f"/api/cases/{core_db.case_id}/web-search", headers=headers()).json()["outcome"] == "ADMITTED"
    run = core_db.rows("SELECT * FROM runs")[0]
    expected = {"empty": "WEB_DISCOVERY_NO_ACTIVITY", "exception": "WEB_DISCOVERY_ERROR", "disabled": "WEB_DISABLED"}
    assert run["status"] == "PARTIAL" and run["stop_reason"] == expected[failure]
    assert core_db.rows("SELECT verdict FROM field_results WHERE field_key='volume'") == [{"verdict": "SINGLE_SOURCE"}]
    assert bool(calls) == (failure != "disabled")


def test_web_audit_does_not_leak_other_case(core_db: CoreDB) -> None:
    run = core_db.run()
    with db.transaction() as connection:
        connection.execute("INSERT INTO cases(id,product_id,tenant_id,created_at) VALUES('other-case',?,'other-tenant',?)", (core_db.product_id, db.now_iso()))
        connection.execute("INSERT INTO web_searches VALUES('other-query','other-case',?,'Other tenant query','test-provider','FALLBACK','[]',0,?)", (run["id"], db.now_iso()))
    with TestClient(create_app()) as client:
        before = core_db.dump()
        assert client.get(f"/api/cases/{core_db.case_id}/web-search", headers=headers()).json() == {"case_id": core_db.case_id, "queries": [], "snapshots": []}
        assert core_db.dump() == before


def test_web_budget_stops_before_discovery(core_db: CoreDB, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_MAX_TOOL_CALLS", "0")
    enable(monkeypatch)
    calls: list[RunContext] = []
    monkeypatch.setattr(web_sources, "discover", provider(core_db, calls))
    with TestClient(create_app()) as client:
        assert client.post(f"/api/cases/{core_db.case_id}/web-search", headers=headers()).json()["outcome"] == "ADMITTED"
    assert not calls
    assert core_db.rows("SELECT status,stop_reason FROM runs") == [{"status": "PARTIAL", "stop_reason": "TOOL_CALL_LIMIT"}]
    assert not core_db.rows("SELECT * FROM web_searches")


def test_unconfirmed_brand_identity_cannot_gain_reference_authority(core_db: CoreDB, monkeypatch: pytest.MonkeyPatch) -> None:
    enable(monkeypatch)
    core_db.source(kind="LISTING")
    calls: list[RunContext] = []
    monkeypatch.setattr(web_sources, "discover", provider(core_db, calls, identity=False))
    with TestClient(create_app()) as client:
        assert client.post(f"/api/cases/{core_db.case_id}/web-search", headers=headers()).json()["outcome"] == "ADMITTED"
    finding = core_db.rows("SELECT verdict,citations_json FROM field_results WHERE field_key='volume'")[0]
    assert finding["verdict"] == "SINGLE_SOURCE"
    assert all(c["source_kind"] != "BRAND_PAGE" for c in db.loads(finding["citations_json"]))
    assert core_db.rows("SELECT * FROM trace_steps WHERE step='web:skip'")


def test_stale_web_admission_does_not_block_a_fresh_request(core_db: CoreDB) -> None:
    with db.transaction() as connection:
        connection.execute("UPDATE cases SET revision=1 WHERE id=?", (core_db.case_id,))
    stale = core_db.event("WEB_SEARCH_REQUESTED", key=f"web:{core_db.case_id}:1")
    assert admit(stale, role=Role.OPERATOR, actor_id="operator").outcome == "NOOP"
    assert not core_db.rows("SELECT * FROM jobs")
    with TestClient(create_app()) as client:
        assert client.post(f"/api/cases/{core_db.case_id}/web-search", headers=headers()).json()["outcome"] == "ADMITTED"
    assert core_db.rows("SELECT revision FROM cases") == [{"revision": 2}]
