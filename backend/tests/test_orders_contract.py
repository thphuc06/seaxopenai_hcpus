"""S4 contracts and ACLs; functional receipt/web/marketplace tests stay separate."""
from contextlib import closing

from fastapi.testclient import TestClient
import pytest

from app import db
from app.api.s4_contracts import (
    BuyerMarketplaceResponse, ReceiptResponse, WebAuditResponse,
)
from app.models import Role


ALL_ROLES = {role.value for role in Role}
ROUTES = [
    ("POST", "/orders", {"product_id": "unseen-container"}, ALL_ROLES),
    ("GET", "/orders", None, ALL_ROLES),
    ("GET", "/orders/unseen-order", None, ALL_ROLES),
    ("GET", "/products/unseen-container/marketplace", None, ALL_ROLES),
    ("POST", "/internal/marketplace/unseen-container/scan", None, {"OPERATOR"}),
    ("POST", "/cases/unseen-case/web-search", None, {"OPERATOR"}),
    ("GET", "/cases/unseen-case/web-search", None, {"OPERATOR", "REVIEWER"}),
    ("GET", "/internal/eval/metrics", None, {"OPERATOR", "REVIEWER"}),
]


def stored_state() -> str:
    with closing(db.connect()) as connection:
        return "\n".join(connection.iterdump())


@pytest.mark.parametrize("role", sorted(ALL_ROLES) + ["UNKNOWN", ""])
def test_s4_role_boundaries_and_no_work_for_unknown_resources(client: TestClient, role: str) -> None:
    before = stored_state()
    for method, path, body, allowed in ROUTES:
        response = client.request(method, "/api" + path, json=body,
                                  headers={"X-Demo-Role": role, "X-Demo-Actor": "contract-observer"})
        if role not in allowed:
            assert response.status_code == 403, (path, response.text)
        elif path in {"/orders", "/internal/eval/metrics"} and method == "GET":
            # Collection/report reads become 200 after Stage B; Stage A returns 501.
            assert response.status_code in {200, 501}, (path, response.text)
        else:
            # Unknown resource IDs become 404 after Stage B; Stage A returns 501.
            assert response.status_code in {404, 501}, (path, response.text)
        assert stored_state() == before


def test_s4_requires_actor_header(client: TestClient) -> None:
    before = stored_state()
    for method, path, body, _ in ROUTES:
        response = client.request(method, "/api" + path, json=body, headers={"X-Demo-Role": "OPERATOR"})
        assert response.status_code == 403
    assert stored_state() == before


@pytest.mark.parametrize("body", [
    {}, {"product_id": ""}, {"product_id": " \t "}, {"product_id": 17},
    {"product_id": "unseen-container", "buyer_id": "another-actor"},
    {"product_id": "unseen-container", "tenant_id": "another-tenant"},
    {"product_id": "unseen-container", "snapshot_hash": "client-supplied"},
    {"product_id": "unseen-container", "case_revision": 999},
])
def test_order_request_rejects_missing_identity_and_client_state(client: TestClient, body: dict[str, object]) -> None:
    before = stored_state()
    response = client.post("/api/orders", json=body,
                           headers={"X-Demo-Role": "BUYER", "X-Demo-Actor": "contract-buyer"})
    assert response.status_code == 422
    assert stored_state() == before


@pytest.mark.parametrize("query", ["", "?as_role=UNKNOWN", "?as_role="])
def test_image_requires_valid_query_role(client: TestClient, query: str) -> None:
    before = stored_state()
    response = client.get("/api/sources/unseen-version/image" + query)
    assert response.status_code == 422
    assert stored_state() == before


def test_image_accepts_query_identity_without_custom_headers(client: TestClient) -> None:
    before = stored_state()
    for role in ALL_ROLES:
        response = client.get("/api/sources/unseen-version/image", params={"as_role": role})
        assert response.status_code in {404, 501}
    assert stored_state() == before


def test_s4_openapi_contracts(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    operations = [
        ("/orders", "post"), ("/orders", "get"), ("/orders/{order_id}", "get"),
        ("/products/{product_id}/marketplace", "get"),
        ("/internal/marketplace/{product_id}/scan", "post"),
        ("/cases/{case_id}/web-search", "post"), ("/cases/{case_id}/web-search", "get"),
        ("/internal/eval/metrics", "get"),
    ]
    for path, method in operations:
        response = paths["/api" + path][method]["responses"]["200"]
        assert response["content"]["application/json"]["schema"]
    components = schema["components"]["schemas"]
    assert components["OrderRequest"]["required"] == ["product_id"]
    assert components["OrderRequest"]["additionalProperties"] is False
    assert paths["/api/orders"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["type"] == "array"
    receipt = components["ReceiptResponse"]
    assert {"snapshot", "snapshot_hash", "chain_head", "hash_valid", "diff", "changed_since_purchase"} <= set(receipt["required"])
    assert receipt["properties"]["snapshot"]["$ref"].endswith("/PassportResponse")
    for name in ("BuyerMarketplaceResponse", "MarketplaceFieldTally", "MarketplaceValueTally"):
        assert components[name]["additionalProperties"] is False
        assert not {"shop", "shops", "findings", "citation", "quote", "seller_source_id", "outlier"} & components[name]["properties"].keys()
    assert "findings" in components["ExpertMarketplaceResponse"]["required"]
    assert "class" in components["WebAuditResult"]["properties"]
    assert set(components["WebAuditResponse"]["required"]) == {"case_id", "queries", "snapshots"}
    # Web-search admission derives its key/budget/revision from server context.
    assert "requestBody" not in paths["/api/cases/{case_id}/web-search"]["post"]
    image = paths["/api/sources/{source_version_id}/image"]["get"]
    assert any(p["name"] == "as_role" and p["in"] == "query" and p["required"] for p in image["parameters"])
    content = image["responses"]["200"]["content"]
    assert "application/json" not in content
    assert set(content) == {"image/png", "image/jpeg", "image/webp"}
    assert all(value["schema"]["format"] == "binary" for value in content.values())


def test_receipt_shape_preserves_absent_fields_and_purchase_state() -> None:
    receipt = ReceiptResponse.model_validate({
        "id": "receipt-variant", "product_id": "different-container", "case_id": "case-variant",
        "placed_at": "2026-10-31T06:00:00Z", "case_revision": 3,
        "snapshot": {"product_id": "different-container", "dataset_origin": "SYNTHETIC",
                     "last_checked_at": None, "run_status": None, "fields": [], "disclaimer": "Source comparison."},
        "snapshot_hash": "a" * 64, "chain_head": None, "hash_valid": True,
        "changed_since_purchase": False,
        "diff": [{"field_key": "volume", "then": None, "now": None, "changed": False}],
    })
    assert receipt.model_dump(mode="json")["diff"][0] == {
        "field_key": "volume", "then": None, "now": None, "changed": False,
    }
    assert receipt.snapshot.fields == []


def test_marketplace_and_web_shapes_preserve_unknown_and_rejected_evidence() -> None:
    public = BuyerMarketplaceResponse(product_id="another-container", scan_id=None, fields=[])
    assert public.model_dump(mode="json") == {
        "audience": "BUYER", "product_id": "another-container", "scan_id": None, "fields": [],
    }
    audit = WebAuditResponse.model_validate({
        "case_id": "another-case", "queries": [{
            "id": "query-variant", "run_id": "run-variant", "query": "container capacity",
            "provider": "offline", "mode": "FALLBACK", "created_at": "2026-10-31T06:00:00Z",
            "results": [{"url": "https://catalogue.example/item", "domain": "catalogue.example",
                         "class": "retailer", "score": None, "decision": "SKIP", "reason": "identity unresolved"}],
        }], "snapshots": [],
    })
    result = audit.model_dump(mode="json", by_alias=True)["queries"][0]["results"][0]
    assert result["class"] == "retailer"
    assert result["score"] is None
    assert result["decision"] == "SKIP"
