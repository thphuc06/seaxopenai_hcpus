"""Exercise the new wiring through the worker, not by replacing the implementation."""
from pathlib import Path
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app import config, db, store, worker
from app.context import RunContext
from app.events.admit import admit
from app.llm import client
from app.main import create_app
from app.models import Readability, Role
from app.pipeline import canon, policy, publish
from app.pipeline.extract import Claim, Extraction
from p1_helpers import CoreDB, core_db
from scripts.sync_check import phase_three_probe


def extracted_skin(sv_id: str, ctx: RunContext) -> Extraction:
    passage = store.passages(sv_id)[0]
    claim = Claim("claim-" + sv_id, sv_id, passage["id"], "skin_type", passage["text"], {}, passage["text"],
                  Readability.READABLE, "FALLBACK", "unit-extraction", "code")
    with db.transaction() as connection:
        connection.execute("INSERT OR IGNORE INTO claims(id,source_version_id,passage_id,field_key,raw_value,normalized_json,readability,extractor,prompt_version,created_at,quote) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (claim.id, sv_id, claim.passage_id, claim.field_key, claim.raw_value, "{}", "READABLE", "FALLBACK", "unit-extraction", db.now_iso(), claim.quote))
    return Extraction([claim], False, "FALLBACK", False)


@pytest.mark.parametrize("surface,value", [("peau sèche", "DRY"), ("teint mixte", "COMBINATION")])
def test_worker_reuses_grounded_canonical_mapping_before_policy(core_db: CoreDB, monkeypatch: pytest.MonkeyPatch, surface: str, value: str) -> None:
    source = core_db.source(text=surface)
    mapping = canon.StoredMapping(value=[value], inci_names=[], source_version_id=source.source_version_id,
        passage_id=source.passage_id, quote=surface, prompt_version=canon.PROMPT_VERSION)
    with db.transaction() as connection:
        connection.execute('INSERT INTO vocab(field,surface,value_json,"by",model,created_at) VALUES(?,?,?,\'model\',?,?)',
            ("skin_type", surface, mapping.model_dump_json(), "prior-model", db.now_iso()))
    monkeypatch.setattr(client, "_call_api", lambda **request: pytest.fail("Cached mapping must not call a provider"))
    event = admit(core_db.event(), role=Role.OPERATOR, actor_id="operator")
    worker.execute_job(event.job_id, extractor=extracted_skin)
    result = core_db.rows("SELECT * FROM field_results WHERE field_key='skin_type' AND superseded_by IS NULL")[0]
    assert result["verdict"] == "SINGLE_SOURCE" and result["seller_attributable"] == 0
    assert db.loads(result["citations_json"])[0]["passage_id"] == source.passage_id


@pytest.mark.parametrize("cap,reason", [(0, "MODEL_CALL_LIMIT"), (24, "REPLAY_MISS")])
def test_worker_reports_canon_failure_as_partial_without_provider(core_db: CoreDB, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cap: int, reason: str) -> None:
    core_db.source(text="peau sèche")
    monkeypatch.setattr(config.settings, "llm_mode", "replay")
    monkeypatch.setattr(config.settings, "model_extract", "gpt-6.1-sol")
    monkeypatch.setattr(config.settings, "model_cheap", "gpt-6.1-sol")
    monkeypatch.setattr(config.settings, "replay_dir", tmp_path / "empty-replay")
    monkeypatch.setattr(config.settings, "run_max_model_calls", cap)
    monkeypatch.setattr(client, "_call_api", lambda **request: pytest.fail("Offline run attempted provider call"))
    event = admit(core_db.event(), role=Role.OPERATOR, actor_id="operator")
    worker.execute_job(event.job_id, extractor=extracted_skin)
    run = core_db.rows("SELECT * FROM runs")[0]
    assert (run["status"], run["stop_reason"]) == ("PARTIAL", reason)


def test_review_queue_reports_result_provenance_not_unrelated_latest_run(core_db: CoreDB) -> None:
    decision = policy.decide("volume", [core_db.source(text="Volume: 83 ml.")], {}, [], [])
    run = core_db.run()
    assert publish.gate(decision, run, {"id": core_db.case_id})
    result = core_db.rows("SELECT id FROM field_results")[0]
    with db.transaction() as connection:
        connection.execute("INSERT INTO review_tasks(id,case_id,field_key,result_id,reason_code,status) VALUES('unit-task',?,'volume',?,'UNIT_REVIEW','OPEN')", (core_db.case_id, result["id"]))
    other = core_db.run()
    with db.transaction() as connection:
        connection.execute("UPDATE runs SET llm_mode='LIVE' WHERE id=?", (other["id"],))
    with TestClient(create_app()) as client:
        queue = client.get("/api/review/queue", headers={"X-Demo-Role": "REVIEWER", "X-Demo-Actor": "reader"}).json()
    task = next(item for item in queue if item["id"] == "unit-task")
    assert task["product_id"] == core_db.product_id and task["dataset_origin"] == "SYNTHETIC"
    assert task["llm_mode"] == "FALLBACK" and task["seller_attributable"] is False


@pytest.mark.parametrize("actor,error,accepted", [("code", None, True), ("llm", None, False), ("human", None, False), ("code", "failed", False)])
def test_operational_effect_probe_requires_code_success(tmp_path: Path, actor: str, error: str | None, accepted: bool) -> None:
    path = tmp_path / "probe.db"
    connection = sqlite3.connect(path)
    try:
        connection.executescript("""
            CREATE TABLE runs(id,case_id,case_revision,created_at,llm_mode,status,stop_reason,model);
            CREATE TABLE trace_steps(run_id,step,actor,error,detail);
            CREATE TABLE passage_scopes(source_version_id,passage_id,scope_match,decided_by,run_id);
            CREATE TABLE passages(id,source_version_id,text);
            CREATE TABLE source_versions(id,source_id);
            CREATE TABLE sources(id,case_id,visibility);
            CREATE TABLE field_results(case_id,superseded_by,explain_json);
            INSERT INTO runs VALUES('current','independent-case',1,'2026-11-01','REPLAY','COMPLETED',NULL,'unit-model');
        """)
        connection.execute("INSERT INTO trace_steps VALUES('current','agent:effect',?,?,?)", (actor, error, db.dumps({"before": "UNCERTAIN", "after": "SINGLE_SOURCE"})))
        connection.commit()
    finally:
        connection.close()
    before = path.read_bytes()
    assert bool(phase_three_probe(path, "independent-case").effects) is accepted
    assert path.read_bytes() == before


@pytest.mark.parametrize("cap,reason", [(0, "MODEL_CALL_LIMIT"), (24, "REPLAY_MISS")])
def test_worker_keeps_cached_mapping_when_learning_another_phrase_fails(core_db: CoreDB, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cap: int, reason: str) -> None:
    known = core_db.source("known-label", text="peau sèche")
    core_db.source("unmapped-reference", kind="BRAND_PAGE", text="teint mixte")
    mapping = canon.StoredMapping(value=["DRY"], inci_names=[], source_version_id=known.source_version_id,
        passage_id=known.passage_id, quote=known.quote, prompt_version=canon.PROMPT_VERSION)
    with db.transaction() as connection:
        connection.execute('INSERT INTO vocab(field,surface,value_json,"by",model,created_at) VALUES(?,?,?,\'model\',?,?)',
            ("skin_type", known.quote, mapping.model_dump_json(), "prior-model", db.now_iso()))
    monkeypatch.setattr(config.settings, "llm_mode", "replay")
    monkeypatch.setattr(config.settings, "model_extract", "gpt-6.1-sol")
    monkeypatch.setattr(config.settings, "model_cheap", "gpt-6.1-sol")
    monkeypatch.setattr(config.settings, "replay_dir", tmp_path / "no-recordings")
    monkeypatch.setattr(config.settings, "run_max_model_calls", cap)
    monkeypatch.setattr(client, "_call_api", lambda **request: pytest.fail("Offline run attempted provider call"))
    event = admit(core_db.event(), role=Role.OPERATOR, actor_id="operator")
    worker.execute_job(event.job_id, extractor=extracted_skin)
    run = core_db.rows("SELECT * FROM runs")[0]
    assert (run["status"], run["stop_reason"]) == ("PARTIAL", reason)
    result = core_db.rows("SELECT * FROM field_results WHERE field_key='skin_type' AND superseded_by IS NULL")
    assert result and result[0]["verdict"] == "SINGLE_SOURCE"
    assert result[0]["seller_attributable"] == 0
    assert db.loads(result[0]["citations_json"])[0]["passage_id"] == known.passage_id
