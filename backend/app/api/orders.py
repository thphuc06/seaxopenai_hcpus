"""Actor-owned immutable receipts and separate marketplace scans."""
from contextlib import closing
from hashlib import sha256
import sqlite3
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from app import chain, db
from app.api import read, marketplace_service
from app.api.dependencies import Actor, OperatorActor
from app.api.s4_contracts import (
    BuyerMarketplaceResponse, ExpertMarketplaceResponse, MarketplaceScanResponse,
    OrderRequest, ReceiptFieldDiff, ReceiptResponse,
)
from app.models import PassportResponse, Role

router = APIRouter()


def _receipt(connection: sqlite3.Connection, row: sqlite3.Row) -> ReceiptResponse:
    snapshot_json = row["snapshot_json"]
    if not isinstance(snapshot_json, str) or sha256(snapshot_json.encode("utf-8")).hexdigest() != row["snapshot_hash"]:
        raise HTTPException(409, "Receipt snapshot integrity check failed")
    try:
        snapshot = PassportResponse.model_validate_json(snapshot_json)
    except ValidationError as exc:
        raise HTTPException(409, "Receipt snapshot is unreadable") from exc
    if snapshot.product_id != row["product_id"]:
        raise HTTPException(409, "Receipt snapshot product mismatch")
    current = read.passport_snapshot(connection, row["product_id"], Role.BUYER)
    before = {field.field_key: field for field in snapshot.fields}
    after = {field.field_key: field for field in current.fields}
    diff = [ReceiptFieldDiff(field_key=key, then=before.get(key), now=after.get(key),
                            changed=before.get(key) != after.get(key)) for key in sorted(before.keys() | after.keys())]
    return ReceiptResponse(id=row["id"], product_id=row["product_id"], case_id=row["case_id"],
        placed_at=row["placed_at"], case_revision=row["case_revision"], snapshot=snapshot,
        snapshot_hash=row["snapshot_hash"], chain_head=row["chain_head"], hash_valid=True,
        changed_since_purchase=any(field.changed for field in diff), diff=diff)


@router.post("/orders", response_model=ReceiptResponse)
def create_order(body: OrderRequest, actor: Actor) -> ReceiptResponse:
    with db.transaction() as connection:
        snapshot = read.passport_snapshot(connection, body.product_id, Role.BUYER)
        case = connection.execute("SELECT id,revision FROM cases WHERE product_id=?", (body.product_id,)).fetchone()
        checked = chain.verify_snapshot(connection, case["id"])
        if not checked.valid:
            raise HTTPException(409, "Result history integrity check failed")
        snapshot_json = db.dumps(snapshot.model_dump(mode="json"))
        identity = uuid4().hex
        connection.execute("INSERT INTO orders(id,product_id,case_id,buyer_id,placed_at,case_revision,snapshot_json,snapshot_hash,chain_head) VALUES(?,?,?,?,?,?,?,?,?)",
            (identity, body.product_id, case["id"], actor.actor_id, db.now_iso(), case["revision"],
             snapshot_json, sha256(snapshot_json.encode("utf-8")).hexdigest(), checked.head))
        row = connection.execute("SELECT * FROM orders WHERE id=?", (identity,)).fetchone()
        return _receipt(connection, row)


@router.get("/orders", response_model=list[ReceiptResponse])
def orders(actor: Actor) -> list[ReceiptResponse]:
    with closing(db.connect()) as connection:
        connection.execute("BEGIN")
        rows = connection.execute("SELECT * FROM orders WHERE buyer_id=? ORDER BY placed_at DESC,id", (actor.actor_id,)).fetchall()
        return [_receipt(connection, row) for row in rows]


@router.get("/orders/{order_id}", response_model=ReceiptResponse)
def order(order_id: str, actor: Actor) -> ReceiptResponse:
    with closing(db.connect()) as connection:
        connection.execute("BEGIN")
        row = connection.execute("SELECT * FROM orders WHERE id=? AND buyer_id=?", (order_id, actor.actor_id)).fetchone()
        if row is None:
            raise HTTPException(404, "Receipt not found")
        return _receipt(connection, row)


@router.get("/products/{product_id}/marketplace", response_model=BuyerMarketplaceResponse | ExpertMarketplaceResponse)
def marketplace(product_id: str, actor: Actor) -> BuyerMarketplaceResponse | ExpertMarketplaceResponse:
    return marketplace_service.view(product_id, actor)


@router.post("/internal/marketplace/{product_id}/scan", response_model=MarketplaceScanResponse)
def scan_marketplace(product_id: str, actor: OperatorActor) -> MarketplaceScanResponse:
    return marketplace_service.scan(product_id, actor)
