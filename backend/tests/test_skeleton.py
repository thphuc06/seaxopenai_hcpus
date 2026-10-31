"""P4 phase-0 behavior and import contract checks."""
from importlib import import_module

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import config
from app.budget import Budget, BudgetExceeded
from app.models import ClaimExtraction, ExtractedClaim, SourceKind

pytestmark = pytest.mark.phase(0)


def test_health_is_read_only_and_does_not_expose_secret(client: TestClient) -> None:
    before = list(config.settings.db_path.parent.iterdir())
    for _ in range(3):
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["llm_mode"] == "fallback"
        assert response.json()["phase"] == config.settings.contest_phase
        assert "openai_api_key" not in response.text.lower()
        assert response.json()["demo_run_delay_s"] == 0
    assert list(config.settings.db_path.parent.iterdir()) == before


def test_health_is_in_openapi_with_response_schema(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    assert schema["paths"]["/api/health"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("HealthResponse")


@pytest.mark.parametrize("name", [
    "config", "models", "context", "budget", "worker", "chain",
    "pipeline.extract", "pipeline.policy", "pipeline.normalize", "pipeline.compare",
    "pipeline.scope_prepass", "agent.scope_resolution", "pipeline.claims_audit",
    "pipeline.gaps", "retrieval.search", "pipeline.web_sources", "pipeline.ocr",
])
def test_stub_imports(name: str) -> None:
    assert import_module(f"app.{name}") is not None


def test_extraction_requires_nullable_fields_and_rejects_extra() -> None:
    claim = {
        "field_key": "volume", "raw_value": None, "passage_id": "unreadable-region",
        "quote": None, "readability": "UNREADABLE", "proposed_skin_types": None,
        "proposed_ingredients": None, "proposed_volume_ml": None,
    }
    assert ExtractedClaim.model_validate(claim).raw_value is None
    with pytest.raises(ValidationError):
        ExtractedClaim.model_validate({key: value for key, value in claim.items() if key != "quote"})
    with pytest.raises(ValidationError):
        ExtractedClaim.model_validate({**claim, "verdict": "CONSISTENT"})
    with pytest.raises(ValidationError):
        ExtractedClaim.model_validate({**claim, "proposed_volume_ml": "75"})


def test_model_schema_is_closed_and_all_fields_required() -> None:
    schema = ClaimExtraction.model_json_schema()
    for model in [schema, *schema.get("$defs", {}).values()]:
        if model.get("type") == "object":
            assert model["additionalProperties"] is False
            assert set(model["required"]) == set(model["properties"])
    assert SourceKind.REGISTRY_RECORD.value == "REGISTRY_RECORD"
    assert SourceKind.WEB_PAGE.value == "WEB_PAGE"


@pytest.mark.parametrize("cap", [0, 2, 5])
def test_budget_counts_and_stops_at_limit(cap: int) -> None:
    budget = Budget(max_model_calls=cap)
    for index in range(cap):
        budget.take_model_call(f"extract:{index}")
    with pytest.raises(BudgetExceeded, match="MODEL_CALL_LIMIT"):
        budget.take_model_call("extract:overflow")
    assert budget.model_calls == cap
    assert budget.stop_reason == "MODEL_CALL_LIMIT"


def test_budget_deadline_and_tool_limit_without_sleep() -> None:
    with pytest.raises(BudgetExceeded, match="RUN_DEADLINE"):
        Budget(deadline_s=0).take_model_call("extract")
    budget = Budget(max_tool_calls=1)
    budget.take_tool("read")
    with pytest.raises(BudgetExceeded, match="TOOL_CALL_LIMIT"):
        budget.take_tool("read-again")
    assert budget.usage()["tool_calls"]["used"] == 1


@pytest.mark.parametrize("name,value", [
    ("LLM_MODE", "unknown"), ("WEB_PROVIDER", "unknown"), ("OCR_ENABLED", "perhaps"),
    ("RUN_DEADLINE_S", "nan"), ("RUN_MAX_MODEL_CALLS", "-1"),
])
def test_invalid_configuration_is_reported(name: str, value: str, monkeypatch: pytest.MonkeyPatch) -> None:
    with monkeypatch.context() as env:
        env.setenv(name, value)
        with pytest.raises(ValueError):
            config.reload_settings()
    config.reload_settings()


def test_reload_preserves_settings_reference_and_resolves_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    original = config.settings
    with monkeypatch.context() as env:
        env.setenv("REPLAY_DIR", "../another-replay-folder")
        env.setenv("RUN_MAX_MODEL_CALLS", "7")
        env.setenv("OPENAI_API_KEY", "unit-test-private-value")
        updated = config.reload_settings()
        assert updated is original
        assert updated.run_max_model_calls == 7
        assert updated.replay_dir == (config.BACKEND_DIR.parent / "another-replay-folder").resolve()
        assert "unit-test-private-value" not in repr(updated)
    config.reload_settings()


def test_config_example_covers_settings() -> None:
    from dataclasses import fields
    text = (config.BACKEND_DIR / ".env.example").read_text(encoding="utf-8")
    keys = {line.split("=", 1)[0] for line in text.splitlines() if line and not line.startswith("#")}
    assert {f.name.upper() for f in fields(config.Settings) if f.name != "model_prices"} <= keys


def test_noop_stubs_return_no_evidence() -> None:
    from app.pipeline.ocr import boxes_for
    from app.retrieval.search import search
    assert boxes_for("unseen-version", "an excerpt") == []
    result = search("unseen-case", "an unrelated query", allowed_sv_ids=[])
    assert result.hits == []
    assert result.stages == {"bm25": []}
