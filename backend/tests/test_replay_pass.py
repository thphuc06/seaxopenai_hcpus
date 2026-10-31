"""Offline bootstrap recording with actual admission/run/replay and global caps."""
from dataclasses import replace
import json
from pathlib import Path

from PIL import Image
from pydantic import ValidationError
import pytest

from app import config, db
from app.budget import BudgetExceeded
from app.llm import client
from test_replay_checkpoint import listing, provider_response
from scripts.record_all import CheckpointError, PassLedger, PriceBook, ROOT, checkpoint, record_pass


@pytest.fixture
def bootstrap(listing: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "fixtures"
    folder = root / "synthetic" / "product"
    folder.mkdir(parents=True)
    (folder / "listing.v1.json").write_text(listing.read_text(encoding="utf-8"), encoding="utf-8")
    (folder / "product.json").write_text(json.dumps({"product_id": "generated-product", "case_id": "generated-case", "tenant_id": "tenant", "dataset_origin": "SYNTHETIC"}), encoding="utf-8")
    event = tmp_path / "bootstrap.json"
    event.write_text(json.dumps({"event_id": "generated-event", "idempotency_key": "generated-key", "type": "BOOTSTRAP",
        "schema_version": "1", "producer": "publisher-panel", "resource": {"kind": "CASE", "id": "generated-case", "version": 1},
        "changed_fields": [], "payload": {"case_id": "generated-case"}, "occurred_at": "2026-10-31T00:00:00Z",
        "correlation_id": "generated-story", "expect": "Fixture annotation, not a gold label"}), encoding="utf-8")
    monkeypatch.setattr(config, "settings", replace(config.settings, fixtures_dir=root, model_cheap=""))
    return event


def test_pass_dry_and_record_replay_keep_ids_and_original_database(bootstrap: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / "pass"
    original = config.settings
    calls = []
    def provider(**request):
        calls.append(request)
        return provider_response(request)
    monkeypatch.setattr(client, "_call_api", provider)
    dry = record_pass([bootstrap], output)
    assert dry.source_count == 1 and dry.network_call_cap == 30 and dry.cost_cap_usd == 2
    assert not output.exists() and calls == []
    report = record_pass([bootstrap], output, execute=True)
    assert report.replay_equal and report.replay_tokens == 0 and report.calls == len(calls) == 1
    assert 0 < report.reserved_usd <= 2
    identities = []
    for mode in ("base", "record", "replay"):
        with db.transaction(output / (mode + ".db")) as connection:
            identities.append([tuple(row) for row in connection.execute("SELECT id,source_version_id FROM passages ORDER BY id")])
    assert identities[0] == identities[1] == identities[2]
    assert record_pass([bootstrap], output, replay_only=True).replay_equal
    assert len(calls) == 1 and config.settings is original
    with pytest.raises(CheckpointError, match="OUTPUT_EXISTS"):
        record_pass([bootstrap], output, execute=True)


def test_ledger_caps_persist_and_unknown_image_cost_blocks_before_request(tmp_path: Path) -> None:
    prices = PriceBook.model_validate_json((ROOT / "backend/app/data/model_prices.json").read_text(encoding="utf-8"))
    path = tmp_path / "ledger.json"
    request = {"model": "gpt-6.1-sol", "input": [], "max_output_tokens": 1}
    ledger = PassLedger(path, prices)
    for _ in range(30):
        ledger.reserve(request)
    with pytest.raises(BudgetExceeded, match="RECORD_PASS_CAP"):
        PassLedger(path, prices).reserve(request)
    assert ledger.state.calls == 30
    fresh = PassLedger(tmp_path / "expensive.json", prices)
    with pytest.raises(BudgetExceeded, match="RECORD_PASS_CAP"):
        fresh.reserve(request | {"max_output_tokens": 300000})
    with pytest.raises(BudgetExceeded, match="VISION_TOKEN_COST_NOT_VERIFIED"):
        fresh.reserve(request | {"input": [{"content": [{"type": "input_image", "image_url": "data:image/png;base64,unused"}]}]})
    assert fresh.state.calls == 0 and not fresh.path.exists()


def test_image_preflight_makes_no_partial_paid_attempt(bootstrap: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = config.settings.fixtures_dir / "synthetic/product"
    image_path = folder / "photo.v1.png"
    Image.new("RGB", (32, 32), "gray").save(image_path)
    (folder / "photo.v1.json").write_text(json.dumps({"source_id": "image-source", "product_id": "generated-product", "kind": "PACKAGING_IMAGE", "version": 1, "dataset_origin": "SYNTHETIC",
        "passages": [{"locator": "front", "text": "Capacity 38 ml."}]}), encoding="utf-8")
    monkeypatch.setattr(client, "_call_api", lambda **kw: pytest.fail("Preflight must block before spending"))
    output = tmp_path / "vision"
    assert record_pass([bootstrap], output).pending_checks == ["VISION_TOKEN_COST_NOT_VERIFIED"]
    with pytest.raises(CheckpointError, match="VISION_TOKEN_COST_NOT_VERIFIED"):
        record_pass([bootstrap], output, execute=True)
    assert not output.exists()


def test_single_listing_checkpoint_replays_coverage_retry(listing: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot = json.loads(listing.read_text(encoding="utf-8"))
    snapshot["passages"][0]["text"] += " Dry skin."
    listing.write_text(json.dumps(snapshot), encoding="utf-8")
    calls = []
    def provider(**request):
        calls.append(request)
        envelope = provider_response(request)
        text = json.loads(envelope.output[0].content[0].text)
        if len(calls) == 2:
            text["claims"].append(text["claims"][0] | {"field_key": "skin_type", "raw_value": "Dry skin", "quote": "Dry skin"})
        envelope.output[0].content[0].text = json.dumps(text)
        return envelope
    monkeypatch.setattr(client, "_call_api", provider)
    report = checkpoint(listing, tmp_path / "coverage", execute=True)
    assert report.replay_equal and report.fallback_equal
    assert [stage.model_calls for stage in report.stages] == [2, 2, 0] and len(calls) == 2


def test_missing_optional_recording_fails_replay_verification(bootstrap: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = config.settings.fixtures_dir / "synthetic/product/listing.v1.json"
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    snapshot["passages"][0]["text"] += " Dry skin."
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    monkeypatch.setattr(client, "_call_api", lambda **request: provider_response(request))
    output = tmp_path / "optional"
    assert record_pass([bootstrap], output, execute=True).replay_equal
    files = list((output / "replay").rglob("*.json"))
    retry = next(p for p in files if json.loads(p.read_text(encoding="utf-8"))["step"] == "extract:retry")
    retry.unlink()  # Deliberately incomplete generated recording, never a shared fixture.
    with pytest.raises(CheckpointError, match="STEP_INCOMPLETE"):
        record_pass([bootstrap], output, replay_only=True)


def test_legacy_checkpoint_rejects_optional_failure(listing: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot = json.loads(listing.read_text(encoding="utf-8"))
    snapshot["passages"][0]["text"] += " Dry skin."
    listing.write_text(json.dumps(snapshot), encoding="utf-8")
    calls = []
    def provider(**request):
        calls.append(request)
        if len(calls) > 1:
            raise client.LLMError("INCOMPLETE")
        return provider_response(request)
    monkeypatch.setattr(client, "_call_api", provider)
    output = tmp_path / "incomplete-legacy"
    with pytest.raises(CheckpointError, match="STEP_INCOMPLETE"):
        checkpoint(listing, output, execute=True)
    assert len(calls) == 2 and not (output / "report.json").exists()


def test_interrupted_spend_journal_cannot_reset_allowance(tmp_path: Path) -> None:
    prices = PriceBook.model_validate_json((ROOT / "backend/app/data/model_prices.json").read_text(encoding="utf-8"))
    path = tmp_path / "ledger.jsonl"
    PassLedger(path, prices).reserve({"model": "gpt-6.1-sol", "input": [], "max_output_tokens": 1})
    with path.open("a", encoding="utf-8") as stream:
        stream.write('{"calls":2,')
    with pytest.raises(ValidationError):
        PassLedger(path, prices)
