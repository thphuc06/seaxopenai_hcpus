"""P4 operational helpers, collected by the standard backend/CI command."""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
import sys

import httpx
from pydantic import BaseModel
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
from app import config
from scripts import demo_reset, seed, sync_check


@pytest.mark.parametrize("mode", ["fallback", "replay"])
@pytest.mark.parametrize("fault", [None, "verdict", "duplicate", "read-side-effect", "model-calls", "http",
                                   "wrong-market", "wrong-mode", "failed-run", "event-model-calls", "event-jobs"])
def test_story_harness_detects_contract_failures(fault: str | None, mode: str) -> None:
    count = {"events": 0, "runs": 0}
    model_calls = 0
    read_calls = 0
    job_count = 1

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal model_calls, read_calls, job_count
        path = request.url.path
        if path.endswith("reset"):
            return httpx.Response(200, json={"status": "reset"})
        if "/fire/" in path:
            name = path.rsplit("/", 1)[1]
            outcome = {"01-bootstrap-demo": "ADMITTED", "02-price-change": "NOOP",
                       "03-duplicate-price-change": "DUPLICATE", "08-rejected-producer": "REJECTED"}[name]
            if outcome != "DUPLICATE" or fault == "duplicate":
                count["events"] += 1
            if outcome == "ADMITTED":
                count["runs"] += 1
            elif fault == "event-model-calls":
                model_calls += 1
            elif fault == "event-jobs":
                job_count += 1
            return httpx.Response(200, json={"event_id": name, "outcome": outcome, "reason": "test",
                                            "job_id": "a-job" if outcome == "ADMITTED" else None,
                                            "stale_fields": []})
        if path.endswith("metrics"):
            return httpx.Response(200, json={"jobs": job_count, "runs": 1, "model_calls": model_calls,
                                            "events": count["events"], "passport_reads": read_calls})
        if path.endswith("runs"):
            return httpx.Response(200, json=[{
                "id": "a-run", "case_id": "a-case", "case_revision": 1, "trigger_event_id": "01-bootstrap-demo",
                "status": "FAILED" if fault == "failed-run" else "COMPLETED",
                "stop_reason": "REPLAY_MISS" if fault == "failed-run" else None,
                "llm_mode": ("FALLBACK" if mode == "replay" else "REPLAY") if fault == "wrong-mode" else mode.upper(),
                "started_at": None, "finished_at": None, "usage": {"model_calls": 0, "tokens_in": 0, "tokens_out": 0},
            }])
        if path.endswith("passport"):
            read_calls += 1
            if fault == "http":
                return httpx.Response(503)
            if fault == "read-side-effect" and read_calls > 2:
                count["runs"] += 1
            if fault == "model-calls" and read_calls > 2:
                model_calls += 1
            fields = [{"field_key": key, "label": "Consistent", "public_text": "Observed value.",
                       "verdict": "INSUFFICIENT" if fault == "verdict" else
                                  ("SINGLE_SOURCE" if key == "skin_type" else "CONSISTENT"),
                       "conflict_locus": None, "freshness": "CURRENT", "review_state": "AUTO_DRAFT",
                       "checked_at": None, "citations": [{"passage_id": "passage", "source_kind": "LISTING",
                           "source_version": 1, "locator": "title", "excerpt": "Observed value"}]}
                      for key in ("volume", "skin_type", "key_ingredients", "notification_number", "responsible_company")]
            return httpx.Response(200, json={"product_id": "unrelated-item", "dataset_origin": "SYNTHETIC",
                "last_checked_at": None, "run_status": "COMPLETED", "fields": fields, "disclaimer": "Sources checked."})
        raise AssertionError(path)

    with httpx.Client(transport=httpx.MockTransport(handler), base_url="http://test") as client:
        result = sync_check.run_phase_one(client, lambda: count.copy(), "unrelated-item",
                                         lambda: {"passage"} if fault == "wrong-market" else set(), expected_mode=mode)
    assert any(check.status == "FAIL" for check in result) == (fault is not None)
    if fault is None:
        assert result[-1].name == "buyer reads x3"


@pytest.mark.parametrize("mode", ["record", "live", "unknown"])
def test_sync_rejects_network_modes_before_creating_state(mode: str, monkeypatch: pytest.MonkeyPatch,
                                                         tmp_path: Path) -> None:
    database = tmp_path / "must-not-exist.db"
    monkeypatch.setenv("DB_PATH", str(database))
    monkeypatch.setenv("LLM_MODE", mode)
    with pytest.raises(SystemExit) as error:
        sync_check.main(["1"])
    assert error.value.code == 2
    assert not database.exists()


def test_sync_refuses_unimplemented_phase_instead_of_reporting_pass() -> None:
    with pytest.raises(SystemExit) as error:
        sync_check.main(["3", "--mode", "fallback"])
    assert error.value.code == 2


def test_settings_isolation_restores_environment_and_reference(monkeypatch: pytest.MonkeyPatch,
                                                              tmp_path: Path) -> None:
    monkeypatch.setenv("LLM_MODE", "fallback")
    config.reload_settings()
    original = config.settings
    previous_path = original.db_path
    with pytest.raises(RuntimeError, match="interrupted"):
        with sync_check.isolated_settings("replay", tmp_path / "temp.db"):
            assert config.settings is original
            assert original.llm_mode == "replay"
            raise RuntimeError("interrupted")
    assert config.settings is original
    assert original.db_path == previous_path
    assert original.llm_mode == "fallback"


@pytest.mark.parametrize("status", [200, 403, 501])
def test_demo_reset_reports_http_result(status: int, capsys: pytest.CaptureFixture[str]) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status, json={"status": "reset"})

    with httpx.Client(transport=httpx.MockTransport(handler), base_url="http://test") as client:
        assert demo_reset.reset_demo(client) == (0 if status == 200 else 1)
    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert requests[0].headers["X-Demo-Role"] == "OPERATOR"
    assert requests[0].url.path == "/api/internal/demo/reset"
    if status != 200:
        assert str(status) in capsys.readouterr().out


def test_demo_reset_connection_error_has_actionable_message(capsys: pytest.CaptureFixture[str]) -> None:
    def unavailable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    with httpx.Client(transport=httpx.MockTransport(unavailable), base_url="http://test") as client:
        assert demo_reset.reset_demo(client) == 1
    assert "backend Action" in capsys.readouterr().out


def test_seed_is_idempotent_and_explicit_reset_restores_state(tmp_path: Path) -> None:
    original_path = config.settings.db_path
    database = tmp_path / "seed.db"
    assert seed.main(["--db", str(database)]) == 0
    with closing(sqlite3.connect(database)) as db:
        original = db.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        assert original > 0
        with db:
            db.execute("UPDATE cases SET revision=9")
    assert seed.main(["--db", str(database)]) == 0
    with closing(sqlite3.connect(database)) as db:
        assert db.execute("SELECT revision FROM cases LIMIT 1").fetchone()[0] == 9
    assert seed.main(["--db", str(database), "--reset"]) == 0
    with closing(sqlite3.connect(database)) as db:
        assert db.execute("SELECT COUNT(*) FROM products").fetchone()[0] == original
        assert db.execute("SELECT MAX(revision) FROM cases").fetchone()[0] == 0
    assert config.settings.db_path == original_path


def test_admission_configuration_rejects_unknown_producer_and_wrong_type() -> None:
    from app.models import EventType
    assert EventType.LISTING_CHANGED in config.PRODUCER_EVENT_TYPES["publisher-panel"]
    assert EventType.SOURCE_REVOKED not in config.PRODUCER_EVENT_TYPES["seller-portal"]
    assert not config.PRODUCER_EVENT_TYPES.get("arbitrary-untrusted-producer", frozenset())
    assert {"stock", "promo"} <= config.NON_MATERIAL_FIELDS
    assert "volume" not in config.NON_MATERIAL_FIELDS
    with pytest.raises(TypeError):
        config.PRODUCER_EVENT_TYPES["arbitrary"] = frozenset()  # type: ignore[index]


@pytest.mark.parametrize("incomplete,refusal", [(False, False), (True, False), (False, True)])
def test_provider_double_matches_installed_sdk_boundary(incomplete: bool, refusal: bool) -> None:
    from app.models import ClaimExtraction
    from test_acceptance import provider_envelope
    payload = ClaimExtraction(source_version_id="unrelated-version", claims=[], ignored_instructions_detected=False)
    response = provider_envelope(payload, "offline-test-model", incomplete=incomplete, refusal=refusal)
    assert response.model == "offline-test-model"
    assert response.usage is not None and response.usage.total_tokens == 15
    if incomplete:
        assert response.status == "incomplete"
        assert response.incomplete_details.reason == "max_output_tokens"
    elif refusal:
        assert response.output[0].content[0].type == "refusal"
    else:
        assert ClaimExtraction.model_validate_json(response.output_text) == payload


def test_scope_double_distinguishes_other_typed_model_steps() -> None:
    from test_acceptance import (
        empty_auxiliary_response, empty_provider_response, schema_has_scope_proposal, typed_proposal_response,
    )

    class Proposal(BaseModel):
        passage_id: str
        applies: str
        anchor_passage_id: str | None
        reason: str

    class ScopeOutput(BaseModel):
        placements: list[Proposal]

    class AuditOutput(BaseModel):
        findings: list[str]
        ignored_instructions: bool

    assert schema_has_scope_proposal(ScopeOutput)
    assert not schema_has_scope_proposal(AuditOutput)
    assert empty_auxiliary_response(AuditOutput).model_dump() == {"findings": [], "ignored_instructions": False}
    calls: list[str] = []
    envelope = empty_provider_response({"text_format": AuditOutput, "model": "offline-test"}, calls)
    assert AuditOutput.model_validate_json(envelope.output_text).findings == []
    assert calls == []
    proposed = {"passage_id": "line-2", "applies": "YES", "anchor_passage_id": "line-1", "reason": "heading"}
    assert typed_proposal_response(ScopeOutput, proposed).model_dump() == {"placements": [proposed]}
