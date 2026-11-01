"""Glassbox reads real stored publication and refuses expert data to buyers."""
from fastapi.testclient import TestClient
from app.main import create_app
from app.models import Role
from app.events.admit import admit
from app.pipeline import policy, publish
from app import chain, db
from p1_helpers import CoreDB, core_db
import pytest


def test_explain_projects_public_and_expert_views_without_writes(core_db: CoreDB) -> None:
    obs = core_db.source(visibility="PRIVATE")
    assert publish.gate(policy.decide("volume", [obs], {}, [], []), core_db.run(), {"id":core_db.case_id})
    assert chain.verify(core_db.case_id).valid
    with TestClient(create_app()) as client:
        before = core_db.dump()
        for role in ("BUYER", "SELLER", "SYSTEM", "REVIEWER", "OPERATOR"):
            response = client.get(f"/api/products/{core_db.product_id}/fields/volume/explain", headers={"X-Demo-Role":role,"X-Demo-Actor":"reader"})
            assert response.status_code == 200
            body = response.json()
            if role in {"REVIEWER", "OPERATOR"}:
                assert body["rules"] and body["sources"] and body["chain_head"]
            else:
                assert body["citations"] == [] and body["hidden_citations"] == 1
                assert not {"rules", "claims", "reviews", "chain_head"} & body.keys()
        assert core_db.dump() == before


def test_observability_counts_noop_and_publication(core_db: CoreDB) -> None:
    obs = core_db.source()
    assert publish.gate(policy.decide("volume", [obs], {}, [], []), core_db.run(), {"id":core_db.case_id})
    result = admit(core_db.event("LISTING_CHANGED", changed_fields=["price"]), role=Role.OPERATOR, actor_id="operator")
    assert result.outcome == "NOOP"
    repeated = core_db.event("LISTING_CHANGED", key="metric-duplicate", changed_fields=["price"])
    assert admit(repeated, role=Role.OPERATOR, actor_id="operator").outcome == "NOOP"
    assert admit(repeated, role=Role.OPERATOR, actor_id="operator").outcome == "DUPLICATE"
    with TestClient(create_app()) as client:
        before = core_db.dump()
        response = client.get("/api/internal/observability", headers={"X-Demo-Role":"REVIEWER","X-Demo-Actor":"reader"})
        assert response.status_code == 200
        assert response.json()["model_calls"]["avoided"] == 3
        assert response.json()["publish_passed"] == 1
        assert response.json()["verdicts"] == {"SINGLE_SOURCE":1}
        assert core_db.dump() == before


@pytest.mark.parametrize("visibility", ["PUBLIC", "PRIVATE"])
def test_buyer_why_explains_stored_finding_and_available_evidence(core_db: CoreDB, visibility: str) -> None:
    obs = core_db.source(visibility=visibility, text="Net contents: 83 ml.")
    assert publish.gate(policy.decide("volume", [obs], {}, [], []), core_db.run(), {"id": core_db.case_id})
    with TestClient(create_app()) as client:
        url = f"/api/products/{core_db.product_id}/fields/volume/explain"
        body = client.get(url, headers={"X-Demo-Role": "BUYER", "X-Demo-Actor": "reader"}).json()
        assert len(body["summaries"]) in {2, 3}
        assert body["public_text"] in body["summaries"]
        assert "one independent source" in " ".join(body["summaries"])
        if visibility == "PUBLIC":
            assert body["citations"][0]["excerpt"] == obs.quote
        else:
            assert body["citations"] == []
            assert "reviewers" in " ".join(body["summaries"])
            assert obs.quote not in str(body)
        with db.transaction() as connection:
            connection.execute("UPDATE field_results SET freshness='STALE' WHERE case_id=?", (core_db.case_id,))
        stale = client.get(url, headers={"X-Demo-Role": "BUYER", "X-Demo-Actor": "reader"}).json()
        assert "needs to be checked again" in " ".join(stale["summaries"])
