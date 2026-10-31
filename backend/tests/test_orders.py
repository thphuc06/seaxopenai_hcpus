"""Receipts use constructed evidence and real publication/admission, without providers."""
from hashlib import sha256

from fastapi.testclient import TestClient
import pytest

from app import chain, db
from app.api import read
from app.events.admit import admit
from app.main import create_app
from app.models import Role
from app.pipeline import policy, publish
from p1_helpers import CoreDB, core_db


def headers(actor: str = "receipt-owner", role: str = "BUYER") -> dict[str, str]:
    return {"X-Demo-Role": role, "X-Demo-Actor": actor}


def publish_volume(core: CoreDB) -> str:
    public = core.source("receipt-public", kind="LISTING")
    private = core.source("receipt-private", visibility="PRIVATE")
    assert publish.gate(policy.decide("volume", [public, private], {}, [], []), core.run(), {"id": core.case_id})
    return private.passage_id


@pytest.mark.parametrize("role", [role.value for role in Role])
def test_order_freezes_public_snapshot_and_actor_identity(core_db: CoreDB, role: str) -> None:
    private_passage = publish_volume(core_db)
    with TestClient(create_app()) as client:
        purchased = client.get(f"/api/products/{core_db.product_id}/passport", headers=headers()).json()
        response = client.post("/api/orders", json={"product_id": core_db.product_id}, headers=headers(role=role))
        assert response.status_code == 200
        receipt = response.json()
        stored = core_db.rows("SELECT * FROM orders")[0]
        assert receipt["snapshot"] == purchased == db.loads(stored["snapshot_json"])
        assert stored["snapshot_hash"] == sha256(stored["snapshot_json"].encode("utf-8")).hexdigest()
        assert receipt["snapshot_hash"] == stored["snapshot_hash"]
        assert receipt["chain_head"] == chain.verify(core_db.case_id).head
        assert receipt["case_revision"] == 0
        assert stored["buyer_id"] == "receipt-owner"
        assert private_passage not in response.text
        assert receipt["hash_valid"] is True and receipt["changed_since_purchase"] is False
        before = core_db.dump()
        counter = read.passport_reads()
        for _ in range(2):
            assert client.get("/api/orders/" + receipt["id"], headers=headers(role=role)).json() == receipt
            assert client.get("/api/orders", headers=headers(role=role)).json() == [receipt]
        assert core_db.dump() == before
        assert read.passport_reads() == counter


def test_receipt_revoke_diff_preserves_original_bytes_and_reads_create_no_work(core_db: CoreDB) -> None:
    publish_volume(core_db)
    with TestClient(create_app()) as client:
        receipt = client.post("/api/orders", json={"product_id": core_db.product_id}, headers=headers()).json()
        original = core_db.rows("SELECT * FROM orders")[0]
        result = admit(core_db.event("SOURCE_REVOKED", resource_kind="SOURCE", resource_id="receipt-private"),
                       role=Role.OPERATOR, actor_id="operator")
        assert result.stale_fields == ["volume"]
        before = core_db.dump()
        updated = client.get("/api/orders/" + receipt["id"], headers=headers()).json()
        assert updated["changed_since_purchase"] is True
        diff = updated["diff"][0]
        assert diff["field_key"] == "volume" and diff["changed"] is True
        assert diff["then"]["freshness"] == "CURRENT" and diff["now"]["freshness"] == "STALE"
        assert updated["snapshot"] == receipt["snapshot"]
        assert updated["case_revision"] == 0
        assert core_db.rows("SELECT revision FROM cases")[0]["revision"] == 1
        assert core_db.rows("SELECT * FROM orders")[0] == original
        assert core_db.dump() == before


def test_empty_purchase_later_gains_visible_field(core_db: CoreDB) -> None:
    with TestClient(create_app()) as client:
        receipt = client.post("/api/orders", json={"product_id": core_db.product_id}, headers=headers()).json()
        assert receipt["snapshot"]["fields"] == [] and receipt["chain_head"] is None
        assert receipt["diff"] == [] and receipt["changed_since_purchase"] is False
        publish_volume(core_db)
        current = client.get("/api/orders/" + receipt["id"], headers=headers()).json()
        assert current["snapshot"]["fields"] == []
        assert current["diff"][0]["then"] is None
        assert current["diff"][0]["now"]["field_key"] == "volume"
        assert current["changed_since_purchase"] is True


@pytest.mark.parametrize("column,value", [("snapshot_json", "{}"), ("snapshot_json", "broken json"),
                                          ("snapshot_hash", "0" * 64)])
def test_snapshot_tampering_fails_both_detail_and_list(core_db: CoreDB, column: str, value: str) -> None:
    with TestClient(create_app()) as client:
        receipt = client.post("/api/orders", json={"product_id": core_db.product_id}, headers=headers()).json()
        with db.transaction() as connection:
            connection.execute(f"UPDATE orders SET {column}=? WHERE id=?", (value, receipt["id"]))
        before = core_db.dump()
        for path in ("/api/orders/" + receipt["id"], "/api/orders"):
            response = client.get(path, headers=headers())
            assert response.status_code == 409
            assert "integrity" in response.json()["detail"]
        assert core_db.dump() == before


@pytest.mark.parametrize("role", [role.value for role in Role])
def test_other_actors_cannot_read_or_enumerate_receipts(core_db: CoreDB, role: str) -> None:
    with TestClient(create_app()) as client:
        receipt = client.post("/api/orders", json={"product_id": core_db.product_id}, headers=headers()).json()
        before = core_db.dump()
        assert client.get("/api/orders/" + receipt["id"], headers=headers("another-actor", role)).status_code == 404
        assert client.get("/api/orders", headers=headers("another-actor", role)).json() == []
        assert client.get("/api/orders").status_code == 403
        assert core_db.dump() == before


def test_broken_result_chain_blocks_purchase_without_partial_order(core_db: CoreDB) -> None:
    publish_volume(core_db)
    with db.transaction() as connection:
        connection.execute("UPDATE field_results SET chain_hash=NULL")
    with TestClient(create_app()) as client:
        before = core_db.dump()
        response = client.post("/api/orders", json={"product_id": core_db.product_id}, headers=headers())
        assert response.status_code == 409
        assert core_db.dump() == before
