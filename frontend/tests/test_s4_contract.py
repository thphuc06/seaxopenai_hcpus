"""Offline contract-4 wire checks in both directions; no running server."""
import json
from pathlib import Path
import subprocess

import pytest
from app.api.s4_contracts import ReceiptResponse, WebAuditResponse

FRONTEND = Path(__file__).resolve().parents[1]


def node(*args: str, payload: object = None) -> object:
    result = subprocess.run(["node", "--import", "./tests/register.mjs", "tests/emit_s4_responses.mjs", *args], cwd=FRONTEND,
        input=None if payload is None else json.dumps(payload), capture_output=True,
        encoding="utf-8", check=True, timeout=30)
    return json.loads(result.stdout)


def test_mock_create_and_detail_match_published_models_separately() -> None:
    for sample in node():
        created = ReceiptResponse.model_validate(sample["creation"])
        detail = ReceiptResponse.model_validate(sample["detail"])
        WebAuditResponse.model_validate(sample["audit"])
        assert sample["scorecard"] == {"available": False}
        assert detail.id == created.id
        assert detail.product_id == created.product_id
        assert detail.snapshot == created.snapshot
        assert created.changed_since_purchase is False
        assert detail.changed_since_purchase is True
        assert {row.field_key for row in detail.diff if row.changed} == {"volume"}
        assert len(detail.diff) == 5
        assert not created.snapshot_hash and created.hash_valid is False


@pytest.mark.parametrize("field_key", ["volume", "responsible_company"])
def test_actual_dto_variants_render_without_private_integrity_data(field_key: str) -> None:
    receipt = ReceiptResponse(id="new-receipt", product_id="new-product", case_id="new-case",
        placed_at="2026-10-31T08:00:00Z", case_revision=23,
        snapshot={"product_id":"new-product", "dataset_origin":"REAL", "last_checked_at":None,
                  "run_status":"RUNNING", "fields":[], "disclaimer":"Stored source comparison."},
        snapshot_hash="private-hash-marker", chain_head="private-chain-marker", hash_valid=True,
        changed_since_purchase=False, diff=[{"field_key":field_key,"then":None,"now":None,"changed":False}])
    audit = WebAuditResponse(case_id="new-case", queries=[{
        "id":"new-query","run_id":"new-run","query":"Different reference query","provider":"offline",
        "mode":"REPLAY","created_at":"2026-10-31T08:00:00Z","results":[{
            "url":"https://catalogue.example/item","domain":"catalogue.example","class":"retailer",
            "score":0,"decision":"SKIP","reason":"Identity unresolved"}]}], snapshots=[])
    output = node("--read-contract", payload={"receipt":receipt.model_dump(mode="json"),
        "audit":audit.model_dump(mode="json", by_alias=True), "scorecard":{"available":False}})
    assert output["receipt"] == receipt.model_dump(mode="json")
    assert output["scorecard"] is None
    assert "Comparison not available" in output["buyer"]
    assert "No changes since purchase" not in output["buyer"]
    assert "private-hash-marker" not in output["buyer"]
    assert "private-chain-marker" not in output["buyer"]
    assert "Current processing status is unavailable" in output["buyer"]
    assert "retailer" in output["expert"] and "Score: 0" in output["expert"]
