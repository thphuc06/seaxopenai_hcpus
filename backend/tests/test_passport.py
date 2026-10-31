from fastapi.testclient import TestClient
import pytest
from app.main import create_app
from app.pipeline import policy, publish
from p1_helpers import CoreDB, core_db

pytestmark = pytest.mark.phase(1)


def headers(role: str) -> dict[str,str]:
    return {"X-Demo-Role":role,"X-Demo-Actor":"unit-reader"}


def test_buyer_reads_are_database_read_only_and_private_citations_are_counted(core_db: CoreDB) -> None:
    public = core_db.source("public",kind="LISTING")
    private = core_db.source("private",visibility="PRIVATE")
    decision = policy.decide("volume",[public,private],{},[],[])
    assert publish.gate(decision,core_db.run(),{"id":core_db.case_id})
    with TestClient(create_app()) as client:
        before = core_db.dump()
        products = client.get("/api/products",headers=headers("BUYER"))
        assert products.status_code == 200
        passport = client.get(f"/api/products/{core_db.product_id}/passport",headers=headers("BUYER")).json()
        assert [c["passage_id"] for c in passport["fields"][0]["citations"]] == [public.passage_id]
        route = f"/api/products/{core_db.product_id}/fields/volume/evidence"
        buyer = client.get(route,headers=headers("BUYER")).json()
        reviewer = client.get(route,headers=headers("REVIEWER")).json()
        assert buyer["hidden_citations"] == 1
        assert reviewer["hidden_citations"] == 0 and len(reviewer["citations"]) == 2
        assert private.passage_id not in str(buyer)
        assert core_db.dump() == before
        metrics = client.get("/api/internal/metrics",headers=headers("OPERATOR")).json()
        assert metrics["passport_reads"] == 1


@pytest.mark.needs("P1", "P2")
def test_internal_read_models_and_reset_after_run(client: TestClient) -> None:
    response = client.post("/api/internal/demo/fire/01-bootstrap-demo",headers=headers("OPERATOR"))
    assert response.status_code == 200
    runs = client.get("/api/internal/runs",headers=headers("REVIEWER"))
    assert runs.status_code == 200 and len(runs.json()) == 1
    detail = client.get("/api/internal/runs/"+runs.json()[0]["id"],headers=headers("REVIEWER"))
    assert detail.status_code == 200
    assert detail.json()["steps"]
    log = client.get("/api/internal/events/log",headers=headers("REVIEWER")).json()
    assert log[0]["job_id"] == response.json()["job_id"]
    assert log[0]["run_id"] == runs.json()[0]["id"]
    assert client.post("/api/internal/demo/reset",headers=headers("OPERATOR")).status_code == 200
    assert client.get("/api/internal/runs",headers=headers("REVIEWER")).json() == []
