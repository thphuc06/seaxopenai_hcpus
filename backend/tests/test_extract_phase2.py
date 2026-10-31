"""Vision, bounded retries and preservation using the actual gateway/storage."""
from dataclasses import replace
import json
from pathlib import Path
from threading import Event

from PIL import Image
import pytest

from app import config, db, store
from app.budget import Budget, BudgetExceeded
from app.context import RunContext
from app.llm import client
from app.models import PUBLIC_FIELDS
from app.pipeline.extract import extract_source_version
from test_extract import context, source, raw_claim, provider_output


@pytest.mark.parametrize("failure", ["INCOMPLETE", "REFUSAL", "API_ERROR", "cap"])
def test_optional_retry_keeps_first_verified_claim(context: RunContext, monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    sv = source(["Capacity 73 ml.", "Dry skin."])
    pid = store.passages(sv)[0]["id"]
    context.mode = "record"
    context.budget = Budget(max_model_calls=1 if failure == "cap" else 2)
    calls = []
    def provider(**request):
        calls.append(request)
        if len(calls) == 1:
            return provider_output(sv, [raw_claim(pid, "73 ml", "73 ml")])
        raise client.LLMError(failure)
    monkeypatch.setattr(client, "_call_api", provider)
    result = extract_source_version(sv, context)
    assert [(c.field_key, c.normalized["value"]) for c in result.claims] == [("volume", 73)]
    with db.transaction() as connection:
        assert connection.execute("SELECT COUNT(*) FROM claims").fetchone()[0] == 1
        detail = json.loads(connection.execute("SELECT detail FROM trace_steps WHERE step='extract:retry' AND actor='code' ORDER BY seq DESC LIMIT 1").fetchone()[0])
        assert detail["retained_claims"] == 1 and detail["stop_reason"]
    assert len(calls) == (1 if failure == "cap" else 2)


def test_coverage_adds_only_missing_pairs_and_caches(context: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    sv = source(["Capacity 73 ml.", "Dry skin."])
    volume, skin = [p["id"] for p in store.passages(sv)]
    context.mode = "record"
    calls = []
    def provider(**request):
        calls.append(request)
        claims = [raw_claim(volume, "73 ml", "73 ml")]
        if len(calls) > 1:
            claims.append(raw_claim(skin, "Dry skin", "Dry skin", field="skin_type"))
        return provider_output(sv, claims)
    monkeypatch.setattr(client, "_call_api", provider)
    result = extract_source_version(sv, context)
    assert len(result.claims) == 2
    assert {c.prompt_version for c in result.claims} == {"extract-v1", "extract-retry-v1"}
    assert extract_source_version(sv, context).cached
    assert len(calls) == 2 and context.budget.model_calls == 2


@pytest.mark.parametrize("extension", ["png", "jpg"])
def test_vision_is_attached_and_unreadable_is_not_guessed(context: RunContext, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, extension: str) -> None:
    image_path = tmp_path / ("label." + extension)
    Image.new("RGB", (24, 24), "gray").save(image_path)
    snapshot = {"source_id": "photo", "product_id": "product", "kind": "PACKAGING_IMAGE", "version": 1,
                "note": "Unreadable region", "passages": [{"locator": "image:front", "text": ""}]}
    sv = store.add_source_version(snapshot, case_id="case", origin="SYNTHETIC", raw_path=str(image_path)).id
    pid = store.passages(sv)[0]["id"]
    context.mode = "record"
    monkeypatch.setattr(config, "settings", replace(config.settings, llm_vision=True))
    calls = []
    def provider(**request):
        calls.append(request)
        return provider_output(sv, [raw_claim(pid, None, None, readability="UNREADABLE")])
    monkeypatch.setattr(client, "_call_api", provider)
    result = extract_source_version(sv, context)
    image_parts = [p for m in calls[0]["input"] for p in m["content"] if p["type"] == "input_image"]
    assert len(image_parts) == 1 and image_parts[0]["detail"] == "high"
    assert image_parts[0]["image_url"].startswith("data:image/png;base64,")
    assert result.claims[0].raw_value is None and result.claims[0].normalized == {}
    assert result.claims[0].prompt_version == "extract-vision-v1"
    context.mode = "fallback"
    fallback = extract_source_version(sv, context)
    assert {c.field_key for c in fallback.claims} == set(PUBLIC_FIELDS)
    assert all(c.readability.value == "UNREADABLE" and c.quote is None for c in fallback.claims)
    assert len(calls) == 1


def test_hard_deadline_returns_before_blocked_provider_and_discards_late_result(context: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    sv = source(["Capacity 17 ml."])
    pid = store.passages(sv)[0]["id"]
    entered, release, returned = Event(), Event(), Event()
    def provider(**request):
        entered.set()
        assert release.wait(5)
        returned.set()
        return provider_output(sv, [raw_claim(pid, "17 ml", "17 ml")])
    monkeypatch.setattr(client, "_call_api", provider)
    context.mode = "record"
    context.budget = Budget(deadline_s=0.2)
    try:
        with pytest.raises(BudgetExceeded, match="RUN_DEADLINE"):
            extract_source_version(sv, context)
        assert entered.is_set() and not returned.is_set()
    finally:
        release.set()
    assert returned.wait(5)
    assert context.budget.model_calls == 1
    assert not list(config.settings.replay_dir.rglob("*.json"))
    with db.transaction() as connection:
        assert connection.execute("SELECT COUNT(*) FROM claims").fetchone()[0] == 0
