"""S2 transport boundary independent of fixtures and Stage B behavior."""
from contextlib import closing

from fastapi.testclient import TestClient
import pytest

from app import db


ROUTES = [
    ("GET", "/api/review/queue", None, {"REVIEWER"}),
    ("GET", "/api/cases/other-case/history", None, {"REVIEWER"}),
    ("POST", "/api/cases/other-case/reviews", {
        "result_id": "other-result", "case_revision": 7,
        "decision": "APPROVE", "reason": "Checked stored passage",
    }, {"REVIEWER"}),
    ("POST", "/api/cases/other-case/evidence", {
        "idempotency_key": "upload-other", "field_keys": ["volume"],
        "content": {"kind": "TEXT", "text": "Container volume: 72 ml"},
    }, {"SELLER", "REVIEWER"}),
]


def snapshot() -> list[tuple[str, int]]:
    with closing(db.connect()) as connection:
        tables = [row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )]
        return [(name, connection.execute('SELECT COUNT(*) FROM "' + name.replace('"', '""') + '"').fetchone()[0])
                for name in tables]


@pytest.mark.parametrize("method,path,payload,allowed", ROUTES)
@pytest.mark.parametrize("role", ["BUYER", "SELLER", "REVIEWER", "OPERATOR", "SYSTEM", "UNKNOWN", ""])
def test_s2_roles_and_no_side_effects(client: TestClient, method: str, path: str,
                                    payload: dict[str, object] | None, allowed: set[str], role: str) -> None:
    before = snapshot()
    response = client.request(method, path, json=payload,
                              headers={"X-Demo-Role": role, "X-Demo-Actor": "contract-reader"})
    # Unknown case IDs may become 404 after Stage B; queue may become 200.
    # Keep the transport/ACL contract usable when the business stubs are replaced.
    if role in allowed:
        assert response.status_code in ({200, 501} if path.endswith("/queue") else {404, 501})
    else:
        assert response.status_code == 403
    assert snapshot() == before


def test_s2_openapi_exposes_closed_typed_contracts(client: TestClient) -> None:
    document = client.get("/openapi.json").json()
    for method, path in [("get", "/api/review/queue"), ("get", "/api/cases/{case_id}/history"),
                         ("post", "/api/cases/{case_id}/reviews"), ("post", "/api/cases/{case_id}/evidence")]:
        operation = document["paths"][path][method]
        schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
        assert "$ref" in schema or "$ref" in schema["items"]
        assert {p["name"].lower() for p in operation["parameters"] if p["in"] == "header"} == {
            "x-demo-role", "x-demo-actor",
        }
    schemas = document["components"]["schemas"]
    for name in ("ReviewRequest", "ReviewOverride", "EvidenceUploadRequest", "TextEvidence", "ImageEvidence"):
        assert schemas[name]["additionalProperties"] is False
    assert schemas["EvidenceUploadRequest"]["properties"]["content"]["discriminator"]["propertyName"] == "kind"
    assert {"results", "events", "reviews", "requests"} <= schemas["CaseHistoryResponse"]["properties"].keys()


@pytest.mark.parametrize("patch", [{"case_revision": -1}, {"case_revision": "7"},
                                   {"decision": "ACCEPT"}, {"reviewer_id": "injected"}, {"reason": ""}])
def test_review_rejects_invalid_fields(client: TestClient, patch: dict[str, object]) -> None:
    payload = dict(ROUTES[2][2] or {})
    payload.update(patch)
    before = snapshot()
    response = client.post(ROUTES[2][1], json=payload,
                           headers={"X-Demo-Role": "REVIEWER", "X-Demo-Actor": "reader"})
    assert response.status_code == 422
    assert snapshot() == before


@pytest.mark.parametrize("content,status", [
    ({"kind": "TEXT", "text": "Different label: 83 ml"}, 501),
    ({"kind": "IMAGE", "media_type": "image/png", "data_base64": "aW1hZ2U="}, 501),
    ({"kind": "IMAGE", "media_type": "text/html", "data_base64": "eA=="}, 422),
    ({"kind": "TEXT", "text": ""}, 422),
    ({"kind": "TEXT", "text": "label", "visibility": "PUBLIC"}, 422),
])
def test_evidence_payload_variants(client: TestClient, content: dict[str, str], status: int) -> None:
    before = snapshot()
    response = client.post("/api/cases/another-case/evidence", json={
        "idempotency_key": "another-upload", "field_keys": ["responsible_company"], "content": content,
    }, headers={"X-Demo-Role": "SELLER", "X-Demo-Actor": "uploader"})
    assert response.status_code in ({404, 501} if status == 501 else {status})
    assert snapshot() == before
