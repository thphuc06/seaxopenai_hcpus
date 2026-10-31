"""Expert routes use real storage and a replaceable external retrieval seam."""
from contextlib import closing

from fastapi.testclient import TestClient
import pytest

from app import chain, db
from app.main import create_app
from app.pipeline import policy, publish
from app.retrieval import search as retrieval
from p1_helpers import CoreDB, core_db

pytestmark = pytest.mark.phase(3)
EXPERT = {"X-Demo-Role": "REVIEWER", "X-Demo-Actor": "expert"}


def snapshot() -> list[str]:
    with closing(db.connect()) as connection:
        return list(connection.iterdump())


@pytest.mark.parametrize("role", ["BUYER", "SELLER", "SYSTEM", "OPERATOR", "REVIEWER", "unknown"])
@pytest.mark.parametrize("path", ["chain", "graph", "search?q=volume"])
def test_route_acl_and_reads(core_db: CoreDB, role: str, path: str) -> None:
    with TestClient(create_app()) as client:
        before = snapshot()
        response = client.get(f"/api/cases/{core_db.case_id}/{path}", headers={"X-Demo-Role": role, "X-Demo-Actor": "reader"})
        assert response.status_code == (200 if role in {"OPERATOR", "REVIEWER"} else 403)
        assert snapshot() == before


def test_graph_projects_citations_dependencies_and_stale_sources(core_db: CoreDB) -> None:
    obs = core_db.source()
    assert publish.gate(policy.decide("volume", [obs], {}, [], []), core_db.run(), {"id": core_db.case_id})
    result_id = str(core_db.rows("SELECT id FROM field_results")[0]["id"])
    with db.transaction() as connection:
        chain.append(connection, result_id)
        connection.execute("UPDATE sources SET status='REVOKED' WHERE id=?", (obs.source_id,))
        connection.execute("UPDATE field_results SET freshness='STALE' WHERE id=?", (result_id,))
    with TestClient(create_app()) as client:
        before = snapshot()
        graph = client.get(f"/api/cases/{core_db.case_id}/graph", headers=EXPERT)
        assert graph.status_code == 200
        body = graph.json()
        source = next(n for n in body["nodes"] if n["kind"] == "source")
        field = next(n for n in body["nodes"] if n["kind"] == "field")
        assert source["status"] == "REVOKED"
        assert "SYNTHETIC" in source["label"]
        assert field["status"] == "STALE"
        assert {edge["relation"] for edge in body["edges"]} == {"depends_on", "cites"}
        assert all(edge["source"] == obs.source_version_id for edge in body["edges"])
        assert client.get(f"/api/cases/{core_db.case_id}/chain", headers=EXPERT).json()["valid"] is True
        assert snapshot() == before


def test_search_supplies_case_current_active_allowlist(core_db: CoreDB, monkeypatch: pytest.MonkeyPatch) -> None:
    old = core_db.source(source_id="versioned")
    current = core_db.source(source_id="versioned", version=2, text="Volume: 84 ml.")
    revoked = core_db.source(source_id="revoked")
    private = core_db.source(source_id="private", visibility="PRIVATE")
    with db.transaction() as connection:
        connection.execute("UPDATE sources SET status='REVOKED' WHERE id=?", (revoked.source_id,))
        connection.execute("INSERT INTO cases(id,product_id) VALUES('outside-case',?)", (core_db.product_id,))
    outside = CoreDB(product_id=core_db.product_id, case_id="outside-case").source(source_id="outside-source")
    calls: list[list[str]] = []

    def search(case_id: str, query: str, *, k: int = 8, mode: str = "auto", allowed_sv_ids: list[str] | None = None) -> retrieval.SearchResult:
        assert case_id == core_db.case_id and query == "volume" and mode == "bm25"
        assert allowed_sv_ids is not None
        calls.append(allowed_sv_ids)
        return retrieval.SearchResult([{"passage_id": current.passage_id, "source_version_id": current.source_version_id}], {"bm25": [{"rank": 1}]})

    monkeypatch.setattr(retrieval, "search", search)
    with TestClient(create_app()) as client:
        before = snapshot()
        response = client.get(f"/api/cases/{core_db.case_id}/search?q=volume&mode=bm25", headers=EXPERT)
        assert response.status_code == 200 and response.json()["hits"]
        assert response.json()["stages"]["bm25"] == [{"rank": 1}]
        assert calls == [sorted([current.source_version_id, private.source_version_id])]
        assert not {old.source_version_id, revoked.source_version_id, outside.source_version_id} & set(calls[0])
        assert snapshot() == before


@pytest.mark.parametrize("path", ["chain", "graph", "search?q=volume"])
def test_missing_case_and_identity(core_db: CoreDB, path: str) -> None:
    with TestClient(create_app()) as client:
        assert client.get(f"/api/cases/absent/{path}", headers=EXPERT).status_code == 404
        assert client.get(f"/api/cases/{core_db.case_id}/{path}").status_code == 403


@pytest.mark.parametrize("query", ["", "?q=", "?q=%20%20", "?q=volume&mode=unsupported"])
def test_invalid_search_is_rejected(core_db: CoreDB, query: str) -> None:
    with TestClient(create_app()) as client:
        assert client.get(f"/api/cases/{core_db.case_id}/search{query}", headers=EXPERT).status_code == 422


def test_graph_and_chain_are_case_isolated(core_db: CoreDB) -> None:
    own = core_db.source(source_id="own-source")
    assert publish.gate(policy.decide("volume", [own], {}, [], []), core_db.run(), {"id": core_db.case_id})
    with db.transaction() as connection:
        connection.execute("INSERT INTO cases(id,product_id) VALUES('elsewhere',?)", (core_db.product_id,))
    other = CoreDB(product_id=core_db.product_id, case_id="elsewhere")
    foreign = other.source(source_id="foreign-source")
    assert publish.gate(policy.decide("volume", [foreign], {}, [], []), other.run(), {"id": other.case_id})
    # Missing-link detection is deliberate tampering, independent of whether
    # main has already enabled automatic append during publication.
    with db.transaction() as connection:
        connection.execute("UPDATE field_results SET chain_seq=NULL,prev_hash=NULL,chain_hash=NULL WHERE case_id=?", (core_db.case_id,))
    with TestClient(create_app()) as client:
        before = snapshot()
        body = client.get(f"/api/cases/{core_db.case_id}/graph", headers=EXPERT).json()
        assert {node["id"] for node in body["nodes"] if node["kind"] == "source"} == {own.source_version_id}
        assert len([node for node in body["nodes"] if node["kind"] == "field"]) == 1
        assert all(edge["source"] == own.source_version_id for edge in body["edges"])
        checked = client.get(f"/api/cases/{core_db.case_id}/chain", headers=EXPERT).json()
        assert checked["rows"] == 1 and checked["valid"] is False
        assert checked["broken_at"] == 1
        assert snapshot() == before
