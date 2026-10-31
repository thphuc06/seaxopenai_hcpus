"""Constructed marketplace evidence exercises real fallback extraction and persistence."""
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app import config, db, store
from app.main import create_app
from app.models import Citation
from app.pipeline import extract, publish
from app.context import RunContext
from p1_helpers import CoreDB, core_db


def headers(role: str = "OPERATOR") -> dict[str, str]:
    return {"X-Demo-Role": role, "X-Demo-Actor": "market-observer"}


@pytest.fixture
def market(core_db: CoreDB, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CoreDB:
    folder = tmp_path / "fixtures" / "marketplace" / core_db.product_id
    folder.mkdir(parents=True)
    for index, (volume, text) in enumerate([(83, "A compact presentation lists volume: 83 ml."),
                                           (83, "Volume: 83 ml. Separate supplier description and label."),
                                           (125, "Container information states 125 ml for this listing.")]):
        snapshot = {"source_id": f"synthetic-market-{index}", "product_id": core_db.product_id, "kind": "LISTING",
            "visibility": "PUBLIC", "version": 1, "dataset_origin": "SYNTHETIC", "shop_name": f"Constructed seller {index}",
            "scope": {"product": core_db.product_id}, "passages": [{"locator": "paragraph:1", "text": text}]}
        (folder / f"{index}.json").write_text(db.dumps(snapshot), encoding="utf-8")
    (folder / "broken.json").write_text("{", encoding="utf-8")
    monkeypatch.setenv("FIXTURES_DIR", str(tmp_path / "fixtures"))
    config.reload_settings()
    return core_db


def test_scan_skips_failed_seller_preserves_passport_and_reads_only(market: CoreDB) -> None:
    with TestClient(create_app()) as client:
        before_passport = client.get(f"/api/products/{market.product_id}/passport", headers=headers("BUYER")).json()
        case_before = market.rows("SELECT * FROM cases")
        response = client.post(f"/api/internal/marketplace/{market.product_id}/scan", headers=headers())
        assert response.status_code == 200
        scan = response.json()
        assert (scan["sellers_processed"], scan["sellers_skipped"], scan["stop_reason"]) == (3, 1, "SELLERS_SKIPPED")
        assert scan["llm_mode"] == "FALLBACK" and scan["findings"] >= 3
        assert market.rows("SELECT * FROM cases") == case_before
        assert not market.rows("SELECT * FROM events") and not market.rows("SELECT * FROM jobs")
        assert not market.rows("SELECT * FROM field_results") and not store.current_sources(market.case_id)
        assert market.rows("SELECT case_id,status FROM runs") == [{"case_id": None, "status": "PARTIAL"}]
        assert len(market.rows("SELECT * FROM review_tasks WHERE reason_code='MARKETPLACE_OUTLIER'")) == 1
        assert client.get(f"/api/products/{market.product_id}/passport", headers=headers("BUYER")).json() == before_passport
        before = market.dump()
        buyer = client.get(f"/api/products/{market.product_id}/marketplace", headers=headers("BUYER"))
        expert = client.get(f"/api/products/{market.product_id}/marketplace", headers=headers("REVIEWER")).json()
        assert buyer.status_code == 200 and buyer.json()["audience"] == "BUYER"
        assert all(f["shop"] not in buyer.text and f["citation"]["excerpt"] not in buyer.text for f in expert["findings"])
        volume = next(f for f in buyer.json()["fields"] if f["field_key"] == "volume")
        assert volume["independent_clusters"] == 3 and volume["majority"] == {"value": 83.0, "unit": "ml", "by": "code"}
        assert sum(f["outlier"] for f in expert["findings"]) == 1
        assert client.get("/api/internal/metrics", headers=headers()).json()["runs"] == 1
        assert client.get("/api/internal/observability", headers=headers()).status_code == 200
        assert client.get("/api/internal/runs", headers=headers()).json() == []
        assert client.get("/api/internal/runs/" + scan["scan_id"], headers=headers()).status_code == 404
        assert market.dump() == before


@pytest.mark.parametrize("role", ["BUYER", "SELLER", "REVIEWER", "SYSTEM"])
def test_scan_acl_before_any_effect(market: CoreDB, role: str) -> None:
    with TestClient(create_app()) as client:
        before = market.dump()
        assert client.post(f"/api/internal/marketplace/{market.product_id}/scan", headers=headers(role)).status_code == 403
        assert market.dump() == before


@pytest.mark.parametrize("change", ["excerpt", "locator", "version", "source", "product"])
def test_marketplace_publication_gate_is_atomic(market: CoreDB, change: str) -> None:
    with TestClient(create_app()) as client:
        assert client.post(f"/api/internal/marketplace/{market.product_id}/scan", headers=headers()).status_code == 200
    row = market.rows("SELECT * FROM marketplace_findings WHERE field_key='volume'")[0]
    with db.transaction() as connection:
        connection.execute("INSERT INTO runs(id,status,llm_mode,created_at) VALUES('new-scan','RUNNING','FALLBACK',?)", (db.now_iso(),))
    citation = Citation.model_validate_json(str(row["citation_json"]))
    finding = publish.MarketplacePublication(market.product_id, "new-scan", str(row["seller_source_id"]), str(row["shop"]),
        "volume", db.loads(str(row["value_json"])), str(row["display"]), str(row["cluster"]), True, citation)
    if change in {"excerpt", "locator", "version"}:
        updates = {"excerpt": {"excerpt": "Text absent from evidence"}, "locator": {"locator": "paragraph:999"},
                   "version": {"source_version": 99}}[change]
        invalid = replace(finding, citation=citation.model_copy(update=updates))
    else:
        invalid = replace(finding, **{"seller_source_id" if change == "source" else "product_id": "unrelated"})
    before = market.dump()
    assert not publish.marketplace_gate([finding, invalid])
    assert market.dump() == before


def test_budget_stop_cannot_publish_tallies_after_citation_gate_failure(market: CoreDB, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_MAX_TOOL_CALLS", "1")
    config.reload_settings()
    original = extract.extract_source_version
    def revoked_after_extraction(source_version_id: str, ctx: RunContext) -> extract.Extraction:
        extracted = original(source_version_id, ctx)
        with db.transaction() as connection:
            connection.execute("UPDATE sources SET status='REVOKED' WHERE id=(SELECT source_id FROM source_versions WHERE id=?)", (source_version_id,))
        return extracted
    monkeypatch.setattr(extract, "extract_source_version", revoked_after_extraction)
    with TestClient(create_app()) as client:
        response = client.post(f"/api/internal/marketplace/{market.product_id}/scan", headers=headers())
        assert response.status_code == 200
        assert response.json()["stop_reason"] == "TOOL_CALL_LIMIT" and response.json()["findings"] == 0
        buyer = client.get(f"/api/products/{market.product_id}/marketplace", headers=headers("BUYER")).json()
        assert buyer["fields"] == []
        assert not market.rows("SELECT * FROM marketplace_findings") and not market.rows("SELECT * FROM review_tasks")
        blocked = market.rows("SELECT detail FROM trace_steps WHERE step='publish:blocked'")
        assert db.loads(blocked[0]["detail"])["reason"] == "MARKETPLACE_CITATION_BLOCKED"


@pytest.mark.parametrize("scope", [{"market": "US", "variant": "83ml"}, {"market": "VN", "variant": "MULTI"}])
def test_marketplace_unmatched_scope_does_not_vote(core_db: CoreDB, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scope: dict[str, str]) -> None:
    folder = tmp_path / "fixtures" / "marketplace" / core_db.product_id
    folder.mkdir(parents=True)
    snapshot = {"source_id": "scoped-market", "product_id": core_db.product_id, "kind": "LISTING", "visibility": "PUBLIC",
        "version": 1, "dataset_origin": "SYNTHETIC", "scope": {"product": core_db.product_id, **scope},
        "passages": [{"locator": "paragraph:1", "text": "For dry skin."}]}
    (folder / "listing.json").write_text(db.dumps(snapshot), encoding="utf-8")
    monkeypatch.setenv("FIXTURES_DIR", str(tmp_path / "fixtures"))
    config.reload_settings()
    with TestClient(create_app()) as client:
        response = client.post(f"/api/internal/marketplace/{core_db.product_id}/scan", headers=headers())
        assert response.status_code == 200 and response.json()["findings"] == 0
        assert client.get(f"/api/products/{core_db.product_id}/marketplace", headers=headers("BUYER")).json()["fields"] == []
        assert not core_db.rows("SELECT * FROM review_tasks")


def test_delivered_real_marketplace_snapshots_remain_outside_passport(client: TestClient) -> None:
    product_id = "REAL-PROD-R1"
    before = client.get(f"/api/products/{product_id}/passport", headers=headers("BUYER")).json()
    response = client.post(f"/api/internal/marketplace/{product_id}/scan", headers=headers())
    assert response.status_code == 200
    assert response.json()["sellers_processed"] == 3 and response.json()["sellers_skipped"] == 0
    assert response.json()["findings"] == 0 and response.json()["llm_mode"] == "FALLBACK"
    expert = client.get(f"/api/products/{product_id}/marketplace", headers=headers("REVIEWER")).json()
    assert expert["findings"] == [] and expert["fields"] == []
    with db.transaction() as connection:
        sources = connection.execute("SELECT dataset_origin,case_id FROM sources WHERE product_id=? AND case_id IS NULL", (product_id,)).fetchall()
        assert len(sources) == 3 and all(row["dataset_origin"] == "REAL" for row in sources)
        reasons = [db.loads(row[0]) for row in connection.execute("SELECT detail FROM trace_steps WHERE run_id=? AND step='marketplace:seller_skipped'", (response.json()["scan_id"],))]
        assert reasons and all(reason["reason"] == "MULTIPLE_VALUES" for reason in reasons)
    assert client.get(f"/api/products/{product_id}/passport", headers=headers("BUYER")).json() == before


def test_marketplace_model_mappings_abstain(market: CoreDB, monkeypatch: pytest.MonkeyPatch) -> None:
    original = extract.extract_source_version
    def learned(source_version_id: str, ctx: RunContext) -> extract.Extraction:
        result = original(source_version_id, ctx)
        return replace(result, claims=[replace(claim, mapped_by="model") for claim in result.claims])
    monkeypatch.setattr(extract, "extract_source_version", learned)
    with TestClient(create_app()) as client:
        response = client.post(f"/api/internal/marketplace/{market.product_id}/scan", headers=headers())
        assert response.status_code == 200 and response.json()["findings"] == 0
        assert not market.rows("SELECT * FROM marketplace_findings") and not market.rows("SELECT * FROM review_tasks")
