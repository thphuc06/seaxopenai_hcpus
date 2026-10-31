"""Static evidence/provenance checks; gold is never inferred from candidate output."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TypeAlias, cast

ROOT = Path(__file__).resolve().parents[2] / "fixtures"
JSON: TypeAlias = str | int | float | bool | None | list["JSON"] | dict[str, "JSON"]


def read(path: Path) -> dict[str, JSON]:
    return cast(dict[str, JSON], json.loads(path.read_text(encoding="utf-8")))


def evidence_rows(value: JSON) -> list[dict[str, JSON]]:
    if isinstance(value, dict):
        if "snapshot" in value and "excerpt" in value:
            return [value]
        return [row for child in value.values() for row in evidence_rows(child)]
    if isinstance(value, list):
        return [row for child in value for row in evidence_rows(child)]
    return []


def test_real_gold_locators_resolve_and_quotes_are_verbatim() -> None:
    gold = read(ROOT / "gold/dev/real.json")
    assert gold["status"] == "DRAFT" and gold["labelled_by"] == "draft:codex"
    assert gold["reviewed_by"] is None and gold["candidate_run_before_labelling"] is False
    assert len(gold["checkpoints"]) == 4
    for row in gold["checkpoints"]:
        assert set(row["expected"]) == {"volume", "skin_type", "key_ingredients", "notification_number", "responsible_company"}
        for key, verdict in row["expected"].items():
            assert row["rationale"][key]["rationale"]
            if verdict != "INSUFFICIENT":
                assert row["rationale"][key]["evidence"]
        for citation in evidence_rows(row):
            source = read(ROOT / citation["snapshot"])
            assert source["product_id"] == row["product_id"]
            assert citation["source_id"] == source["source_id"]
            passage = next(p for p in source["passages"] if p["id"] == citation["passage_id"])
            assert passage["locator"] == citation["locator"]
            assert citation["excerpt"] in passage["text"]


def test_real_captures_have_hashes_timestamps_and_no_fabricated_scope() -> None:
    sources = [read(p) for p in (ROOT / "real").rglob("*.v1.json")]
    assert len(sources) == 8
    for source in sources:
        assert source["dataset_origin"] == "REAL"
        assert source["uri"].startswith("https://") and source["requested_uri"].startswith("https://")
        assert source["captured_at"].startswith("2026-10-31T")
        assert len(source["raw_sha256"]) == 64
        text = "\n".join(p["text"] for p in source["passages"])
        assert source["cleaned_sha256"] == hashlib.sha256(text.encode("utf-8")).hexdigest()
        assert "scope" not in source
        assert source["passages"][0]["locator"] == "title"
        assert len({p["locator"] for p in source["passages"]}) == len(source["passages"])


def test_real_events_reference_captured_listings_and_distinct_idempotency_keys() -> None:
    keys: set[str] = set()
    for path in sorted((ROOT / "events").glob("1[4-7]-*.json")):
        event = read(path)
        product = next(read(p) for p in (ROOT / "real").rglob("product.json") if read(p)["product_id"] == event["payload"]["product_id"])
        assert event["payload"]["case_id"] == event["resource"]["id"] == product["case_id"]
        assert event["idempotency_key"] not in keys
        keys.add(event["idempotency_key"])
        assert product["web"]["enabled"] is True
        assert any(read(p)["kind"] == "LISTING" for p in (ROOT / "real").rglob("*.v1.json") if read(p)["product_id"] == product["product_id"])
    assert len(keys) == 4


def test_blind_table_is_explicitly_planned_not_evaluated_or_reviewed() -> None:
    gold = read(ROOT / "gold/blind/expected-set1.json")
    assert gold["status"] == "DRAFT" and gold["labelled_by"] == "draft:codex"
    assert gold["first_candidate_run"] is None and gold["ready_for_evaluation"] is False
    assert gold["fixture_status"] == "PLANNED_NOT_MATERIALIZED"
    assert len(gold["cases"]) == 12
    assert len({row["product_id"] for row in gold["cases"]}) == 12
    for row in gold["cases"]:
        assert row["product_id"].startswith("BLIND-") and row["status"] == "DRAFT"
        assert len(row["expected"]) == 5 and row["planted_conditions"]
        assert set(row["rationale"]) == set(row["expected"])


def test_r4_wrong_size_retailer_is_same_family_and_identifiers_remain_missing() -> None:
    sources = [read(p) for p in (ROOT / "real/r4-effaclar-gel").glob("*.v1.json")]
    assert len({source["family"] for source in sources}) == 1
    assert {source["kind"] for source in sources} == {"LISTING", "WEB_PAGE"}
    row = next(r for r in read(ROOT / "gold/dev/real.json")["checkpoints"] if r["product_id"] == "REAL-PROD-R4")
    assert row["expected"]["notification_number"] == row["expected"]["responsible_company"] == "INSUFFICIENT"
    assert row["claims"][0]["expected"] == "INSUFFICIENT"
