"""Independent upload/read regressions without a model or real fixtures."""
from pathlib import Path
from fastapi.testclient import TestClient
import pytest
from app import config, db
from app.api import read
from app.main import create_app
from app.pipeline import policy, publish
from p1_helpers import CoreDB, core_db


def test_upload_retry_does_not_replace_evidence(core_db: CoreDB, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIXTURES_DIR",str(tmp_path))
    config.reload_settings()
    with TestClient(create_app()) as client:
        body = {"idempotency_key":"upload-17","field_keys":["volume"],"content":{"kind":"TEXT","text":"Volume: 83 ml."}}
        headers = {"X-Demo-Role":"SELLER","X-Demo-Actor":"seller-17"}
        first = client.post(f"/api/cases/{core_db.case_id}/evidence",json=body,headers=headers)
        assert first.status_code == 200
        assert first.json()["outcome"] == "ADMITTED"
        files = {p.name:p.read_bytes() for p in (tmp_path/"uploads").iterdir()}
        before = core_db.dump()
        body["content"] = {"kind":"TEXT","text":"Volume: 91 ml."}
        duplicate = client.post(f"/api/cases/{core_db.case_id}/evidence",json=body,headers=headers)
        assert duplicate.json()["outcome"] == "DUPLICATE"
        assert core_db.dump() == before
        assert {p.name:p.read_bytes() for p in (tmp_path/"uploads").iterdir()} == files
        assert core_db.rows("SELECT visibility FROM sources")[0]["visibility"] == "PRIVATE"


def test_buyer_gets_only_claim_count_and_creates_no_rows(core_db: CoreDB) -> None:
    from dataclasses import replace
    obs = core_db.source(text="Fragrance-free statement. INCI: Parfum.")
    key = "claim:free_from:fragrance"
    claim = replace(obs,field_key=key,normalized={"value":"fragrance"})
    inci = replace(obs,field_key="inci_list",normalized={"value":["Parfum"]})
    decision = policy.decide(key,[claim,inci],{},[],[])
    assert publish.gate(decision,core_db.run(),{"id":core_db.case_id})
    with TestClient(create_app()) as client:
        before = core_db.dump()
        headers = {"X-Demo-Role":"BUYER","X-Demo-Actor":"reader"}
        passport = client.get(f"/api/products/{core_db.product_id}/passport",headers=headers)
        assert passport.status_code == 200 and passport.json()["fields"] == []
        assert client.get(f"/api/products/{core_db.product_id}/fields/{key}/evidence",headers=headers).status_code == 404
        product = client.get("/api/products",headers=headers).json()[0]
        assert product["presentation"]["passport_metadata"]["pending_claims"] == 1
        assert key not in product["presentation"]["passport_metadata"]["hidden_citations"]
        assert core_db.dump() == before
