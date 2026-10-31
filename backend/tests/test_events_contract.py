"""P1 Stage A: S1 route/schema/ACL contracts independent of demo inputs."""
from collections.abc import Callable
from contextlib import closing

from fastapi.testclient import TestClient
import pytest

from app import db


ROUTES = [
    ("get", "/api/products", "BUYER"),
    ("get", "/api/products/arbitrary-item/passport", "BUYER"),
    ("get", "/api/products/arbitrary-item/fields/volume/evidence", "BUYER"),
    ("post", "/api/internal/events", "OPERATOR"),
    ("get", "/api/internal/events/catalog", "OPERATOR"),
    ("get", "/api/internal/events/log", "OPERATOR"),
    ("post", "/api/internal/demo/fire/arbitrary-event", "OPERATOR"),
    ("post", "/api/internal/demo/reset", "OPERATOR"),
    ("get", "/api/internal/runs", "REVIEWER"),
    ("get", "/api/internal/runs/arbitrary-run", "REVIEWER"),
    ("get", "/api/internal/metrics", "OPERATOR"),
]


def test_all_s1_routes_publish_response_models_and_identity_headers(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    expected = [
        ("get", "/api/products"),
        ("get", "/api/products/{product_id}/passport"),
        ("get", "/api/products/{product_id}/fields/{field_key}/evidence"),
        ("post", "/api/internal/events"),
        ("get", "/api/internal/events/catalog"),
        ("get", "/api/internal/events/log"),
        ("post", "/api/internal/demo/fire/{name}"),
        ("post", "/api/internal/demo/reset"),
        ("get", "/api/internal/runs"),
        ("get", "/api/internal/runs/{run_id}"),
        ("get", "/api/internal/metrics"),
    ]
    for method, path in expected:
        operation = paths[path][method]
        schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
        assert "$ref" in schema or (schema["type"] == "array" and "$ref" in schema["items"])
        headers = {item["name"].lower() for item in operation["parameters"] if item["in"] == "header"}
        assert headers == {"x-demo-role", "x-demo-actor"}


@pytest.mark.parametrize("method,path,role", ROUTES)
@pytest.mark.parametrize("headers", [
    {}, {"X-Demo-Role": "BUYER"},
    {"X-Demo-Role": "UNKNOWN", "X-Demo-Actor": "reader"},
    {"X-Demo-Role": "OPERATOR", "X-Demo-Actor": "   "},
])
def test_s1_rejects_missing_or_invalid_identity(
    client: TestClient, method: str, path: str, role: str, headers: dict[str, str],
) -> None:
    assert client.request(method, path, headers=headers).status_code == 403


@pytest.mark.parametrize("method,path", [(method, path) for method, path, _ in ROUTES if "/internal/" in path])
@pytest.mark.parametrize("role", ["BUYER", "SELLER"])
def test_internal_routes_reject_unprivileged_roles(
    client: TestClient, method: str, path: str, role: str,
) -> None:
    assert client.request(method, path, headers={"X-Demo-Role": role, "X-Demo-Actor": "visitor"}).status_code == 403


def test_buyer_reads_do_not_create_pipeline_rows(
    client: TestClient, counts: Callable[[], dict[str, int]],
) -> None:
    before = counts()
    headers = {"X-Demo-Role": "BUYER", "X-Demo-Actor": "unrelated-reader"}
    for method, path, role in ROUTES:
        if role == "BUYER":
            client.request(method, path, headers=headers)
    assert counts() == before


def test_event_envelope_is_closed_and_identity_is_not_payload_controlled(client: TestClient) -> None:
    payload = {
        "event_id": "input-event", "idempotency_key": "input-key", "type": "BOOTSTRAP",
        "schema_version": "1", "producer": "test-producer",
        "resource": {"kind": "CASE", "id": "unrelated-case", "version": 1},
        "changed_fields": [], "payload": {}, "occurred_at": "2026-10-31T00:00:00Z",
        "correlation_id": "input-correlation", "role": "SYSTEM",
    }
    response = client.post("/api/internal/events", json=payload, headers={
        "X-Demo-Role": "OPERATOR", "X-Demo-Actor": "input-operator",
    })
    assert response.status_code == 422
    assert any(error["type"] == "extra_forbidden" for error in response.json()["detail"])


def test_collection_and_evidence_contracts_expose_required_metadata(client: TestClient) -> None:
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    assert {"hidden_citations", "llm_mode"} <= schemas["PassportMetadata"]["properties"].keys()
    assert {"citations", "hidden_citations"} <= schemas["EvidenceResponse"]["properties"].keys()
    assert {"name", "type", "product_id", "resource", "expect"} <= schemas["EventCatalogItem"]["properties"].keys()
    assert {"passport_reads", "model_calls"} <= schemas["MetricsResponse"]["properties"].keys()
    assert schemas["PassportResponse"]["additionalProperties"] is False


def test_buyer_reads_preserve_all_stored_rows_for_existing_and_unknown_products(client: TestClient) -> None:
    with closing(db.connect()) as connection:
        product_ids = [row[0] for row in connection.execute("SELECT id FROM products ORDER BY id")]
        assert product_ids
        before = tuple(connection.iterdump())
        headers = {"X-Demo-Role": "BUYER", "X-Demo-Actor": "another-reader"}
        client.get("/api/products", headers=headers)
        for product_id in [*product_ids, "unknown-other-item"]:
            client.get(f"/api/products/{product_id}/passport", headers=headers)
            for field in ("volume", "skin_type", "key_ingredients", "notification_number", "responsible_company"):
                client.get(f"/api/products/{product_id}/fields/{field}/evidence", headers=headers)
        assert tuple(connection.iterdump()) == before


@pytest.mark.parametrize("method,path,role", [
    *ROUTES,
    ("post", "/api/internal/events", "SYSTEM"),
    ("get", "/api/internal/runs", "OPERATOR"),
    ("get", "/api/internal/events/log", "REVIEWER"),
])
def test_authorized_roles_reach_route_without_identity_or_schema_rejection(
    client: TestClient, method: str, path: str, role: str,
) -> None:
    payload = {
        "event_id": "contract-event", "idempotency_key": "contract-request", "type": "BOOTSTRAP",
        "schema_version": "1", "producer": "contract-producer",
        "resource": {"kind": "CASE", "id": "contract-case", "version": 1},
        "changed_fields": [], "payload": {}, "occurred_at": "2026-10-31T00:00:00Z",
        "correlation_id": "contract-correlation",
    }
    response = client.request(method, path, headers={
        "X-Demo-Role": role, "X-Demo-Actor": "contract-actor",
    }, json=payload if path == "/api/internal/events" else None)
    assert response.status_code not in {401, 403, 422}
