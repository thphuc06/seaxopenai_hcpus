"""S3 schema and authorization boundaries, independent of pipeline behavior."""
from contextlib import closing

from fastapi.testclient import TestClient
import pytest

from app import db
from app.models import Role


ROUTES = [
    ("/products/arbitrary-product/fields/volume/explain", {r.value for r in Role}),
    ("/internal/observability", {"REVIEWER", "OPERATOR"}),
    ("/cases/arbitrary-case/chain", {"REVIEWER", "OPERATOR"}),
    ("/cases/arbitrary-case/graph", {"REVIEWER", "OPERATOR"}),
    ("/cases/arbitrary-case/search?q=container", {"REVIEWER", "OPERATOR"}),
    ("/internal/runs/arbitrary-run/otel", {"REVIEWER", "OPERATOR"}),
]


def snapshot() -> str:
    with closing(db.connect()) as connection:
        return "\n".join(connection.iterdump())


@pytest.mark.parametrize("path,allowed", ROUTES)
@pytest.mark.parametrize("role", [r.value for r in Role] + ["UNKNOWN", ""])
def test_glassbox_acl_and_read_only(client: TestClient, path: str, allowed: set[str], role: str) -> None:
    before = snapshot()
    response = client.get("/api" + path, headers={"X-Demo-Role": role, "X-Demo-Actor": "contract-reader"})
    if role not in allowed:
        assert response.status_code == 403
    else:
        # Unknown resource IDs become 404 after Stage B; global counters become 200.
        assert response.status_code in {200, 404, 501}
    assert snapshot() == before


@pytest.mark.parametrize("query", ["", "?q=", "?q=container&mode=unsupported"])
def test_search_requires_valid_query(client: TestClient, query: str) -> None:
    response = client.get("/api/cases/arbitrary-case/search" + query,
                          headers={"X-Demo-Role": "REVIEWER", "X-Demo-Actor": "contract-reader"})
    assert response.status_code == 422


def test_s3_openapi_models(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    for path in ["/products/{product_id}/fields/{field_key}/explain", "/internal/observability",
                 "/cases/{case_id}/chain", "/cases/{case_id}/graph", "/cases/{case_id}/search",
                 "/internal/runs/{run_id}/otel"]:
        response = schema["paths"]["/api" + path]["get"]["responses"]["200"]
        assert response["content"]["application/json"]["schema"]
    buyer = schema["components"]["schemas"]["BuyerExplanation"]
    assert buyer["additionalProperties"] is False
    assert not {"rules", "claims", "chain_head", "reviews", "sources"} & buyer["properties"].keys()
