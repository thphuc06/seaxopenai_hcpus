"""Story CLI checks with actual isolated pipeline and the documented provider seam."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys

from openai.types.responses import Response
from openai import APIStatusError
import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import config
from app.budget import BudgetExceeded
from app.llm import client
from scripts.record_all import (
    CheckpointError, PassLedger, PriceBook, ROOT, StoryItem, StoryPlan,
    main, story_pass, story_plan,
)
from test_replay_checkpoint import listing, provider_response
from test_replay_pass import bootstrap


def plan_for(bootstrap: Path, *, max_calls: int = 30, max_usd: float = 2) -> StoryPlan:
    plan = story_plan(storyboard=bootstrap.parent / "no-board.md", max_calls=max_calls, max_usd=max_usd)
    # Small independent source corpus, not a replacement of the repo's event set.
    from app.models import EventEnvelope
    payload = json.loads(bootstrap.read_text(encoding="utf-8"))
    payload.pop("expect")
    plan.items = [StoryItem(name="generated", event=EventEnvelope.model_validate(payload))]
    plan.missing_inputs = []
    plan.blockers = []
    return plan


def test_order_story_actions_remaining_events_then_blind_without_gold(bootstrap: Path, tmp_path: Path) -> None:
    root = config.settings.fixtures_dir
    event_dir = root / "events"
    event_dir.mkdir()
    payload = json.loads(bootstrap.read_text(encoding="utf-8"))
    for index in range(1, 18):
        (event_dir / f"{index:02}-generated.json").write_text(json.dumps(payload | {"event_id": f"evt-{index}"}), encoding="utf-8")
    blind = root / "blind/set1/variant"
    blind.mkdir(parents=True)
    product = {"product_id": "unrelated", "case_id": "unrelated-case", "dataset_origin": "SYNTHETIC"}
    (blind / "product.json").write_text(json.dumps(product), encoding="utf-8")
    (blind / "listing.v1.json").write_text("{}", encoding="utf-8")
    (root / "gold").mkdir()
    (root / "gold/invalid.json").write_text("not JSON: must not read", encoding="utf-8")
    board = tmp_path / "story.md"
    board.write_text("prose event04\n| 1 · start | `event-btn-12-generated`, event02, event12 | callout event03 |\n| 2 · next | event01 | hold |", encoding="utf-8")
    plan = story_plan(storyboard=board)
    assert [item.name for item in plan.items[:4]] == ["12-generated", "02-generated", "01-generated", "03-generated"]
    assert len(plan.items) == 18 and plan.items[-1].name == "blind/set1/variant"
    assert not plan.missing_inputs
    assert all(not name.startswith("gold/") for name in plan.input_hashes)
    assert plan.estimated_calls_upper == 18 * config.settings.run_max_model_calls
    assert plan.items[-1].event == story_plan(storyboard=board).items[-1].event


def test_missing_story_inputs_prices_and_default_dry_run_are_explicit(bootstrap: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(config, "settings", replace(config.settings, model_agent="unknown-price"))
    monkeypatch.setattr(client, "_call_api", lambda **kw: pytest.fail("dry run called provider"))
    output = tmp_path / "dry"
    monkeypatch.setattr(sys, "argv", ["record_all.py", "--output-dir", str(output), "--dry-run"])
    assert main() == 1
    text = capsys.readouterr().out
    assert '"dry_run": true' in text and "MODEL_PRICE_NOT_REVIEWED" in text
    assert "events/01-*.json" in text and "blind/set1/*/product.json" in text
    assert not output.exists()
    plan = story_plan(storyboard=tmp_path / "missing.md")
    with pytest.raises(CheckpointError, match="STORY_PREFLIGHT_BLOCKED"):
        story_pass(plan, output, execute=True)


@pytest.mark.parametrize("calls,usd", [(0, 1), (-1, 1), (1, 0), (1, -1), (1, float("inf")), (1, float("nan"))])
def test_invalid_caps_fail_closed(calls: int, usd: float, tmp_path: Path) -> None:
    with pytest.raises(CheckpointError, match="FINITE_POSITIVE_CAPS_REQUIRED"):
        story_plan(max_calls=calls, max_usd=usd)


@pytest.mark.parametrize("calls,usd", [(1, 2), (20, 0.000001)])
def test_custom_ledger_limits_persist_before_sending(calls: int, usd: float, tmp_path: Path) -> None:
    prices = PriceBook.model_validate_json((ROOT / "backend/app/data/model_prices.json").read_text(encoding="utf-8"))
    ledger = PassLedger(tmp_path / "ledger", prices, max_calls=calls, max_usd=usd)
    request = {"model": "gpt-6.1-sol", "input": [], "max_output_tokens": 1}
    if calls == 1:
        ledger.reserve(request)
        ledger = PassLedger(ledger.path, prices, max_calls=calls, max_usd=usd)
    with pytest.raises(BudgetExceeded, match="RECORD_PASS_CAP"):
        ledger.reserve(request)
    assert ledger.state.calls == (1 if calls == 1 else 0)


def test_story_record_replay_isolated_stable_counted_and_immutable(bootstrap: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan = plan_for(bootstrap)
    output = tmp_path / "story"
    calls: list[dict[str, object]] = []
    def provider(**request: object) -> Response:
        calls.append(request)
        return provider_response(request)
    monkeypatch.setattr(client, "_call_api", provider)
    application = tmp_path / "user.db"
    application.write_bytes(b"untouched application state")
    monkeypatch.setattr(config, "settings", replace(config.settings, db_path=application))
    original = config.settings
    dry = story_pass(plan, output)
    assert dry.dry_run and not output.exists() and not calls
    recorded = story_pass(plan, output, execute=True)
    assert recorded.complete and recorded.network_calls == len(calls) == 1
    assert not recorded.not_recorded
    artifacts = {p: p.read_bytes() for p in output.rglob("*") if p.is_file()}
    replayed = story_pass(plan, output, mode="replay", execute=True)
    assert replayed.complete and replayed.replay_equal and replayed.network_calls == 0
    assert replayed.receipts[0].model_calls == 1 and replayed.receipts[0].mode == "REPLAY"
    assert len(calls) == 1
    assert artifacts == {p: p.read_bytes() for p in artifacts}
    assert application.read_bytes() == b"untouched application state" and config.settings is original
    with pytest.raises(CheckpointError, match="OUTPUT_EXISTS"):
        story_pass(plan, output, execute=True)
    changed = plan.model_copy(update={"fingerprint": "changed"})
    with pytest.raises(CheckpointError, match="STORY_INPUT_IDENTITY_CHANGED"):
        story_pass(changed, output, mode="replay", execute=True)


def test_replay_miss_is_not_fallback_or_success(bootstrap: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client, "_call_api", lambda **kw: pytest.fail("Replay must not contact provider"))
    report = story_pass(plan_for(bootstrap), tmp_path / "absent", mode="replay", execute=True, replay_dir=tmp_path / "empty-replay")
    assert not report.complete and report.network_calls == 0
    assert report.not_recorded == ["generated"] and report.fallback == []
    assert any("REPLAY_MISS" in reason for reason in report.receipts[0].stop_reasons)
    assert report.receipts[0].model_calls == 1


def test_cap_keeps_partial_and_labels_subsequent_fallback(bootstrap: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan = plan_for(bootstrap, max_usd=0.000001)
    second = plan.items[0].event.model_copy(update={"event_id": "later", "idempotency_key": "later"})
    plan.items.append(StoryItem(name="later", event=second))
    monkeypatch.setattr(client, "_call_api", lambda **kw: pytest.fail("Reservation must reject before provider"))
    report = story_pass(plan, tmp_path / "capped", execute=True)
    assert report.network_calls == 0 and report.reserved_usd == 0
    assert report.not_recorded == ["generated", "later"]
    assert report.fallback == ["later"] and report.receipts[1].mode == "FALLBACK"
    assert report.receipts[0].status == "PARTIAL" and "RECORD_PASS_CAP" in report.receipts[0].stop_reasons


def test_fallback_execution_never_creates_recording(bootstrap: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client, "_call_api", lambda **kw: pytest.fail("Fallback called provider"))
    output = tmp_path / "fallback"
    report = story_pass(plan_for(bootstrap), output, mode="fallback", execute=True)
    assert report.fallback == ["generated"] and report.network_calls == 0
    assert report.receipts[0].model_calls == 0 and report.receipts[0].status == "COMPLETED"
    assert report.not_recorded == ["generated"] and not output.exists()


def test_source_changes_invalidate_plan_identity(bootstrap: Path) -> None:
    before = story_plan()
    path = config.settings.fixtures_dir / "synthetic/product/listing.v1.json"
    path.write_text(path.read_text(encoding="utf-8").replace("38 ml", "47 ml"), encoding="utf-8")
    after = story_plan()
    assert before.fingerprint != after.fingerprint
    assert after.input_hashes["synthetic/product/listing.v1.json"] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_source_less_product_is_reported_as_missing_input(bootstrap: Path) -> None:
    (config.settings.fixtures_dir / "synthetic/product/listing.v1.json").unlink()
    plan = story_plan()
    assert "synthetic/product:sources" in plan.missing_inputs


def test_stale_plan_rejected_before_attempt(bootstrap: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan = plan_for(bootstrap)
    path = config.settings.fixtures_dir / "synthetic/product/listing.v1.json"
    path.write_text(path.read_text(encoding="utf-8").replace("38 ml", "53 ml"), encoding="utf-8")
    monkeypatch.setattr(client, "_call_api", lambda **kw: pytest.fail("Stale plan called provider"))
    output = tmp_path / "stale"
    with pytest.raises(CheckpointError, match="STORY_INPUT_IDENTITY_CHANGED"):
        story_pass(plan, output, execute=True)
    assert not output.exists()


def test_new_source_after_plan_is_rejected_before_seeding(bootstrap: Path, tmp_path: Path) -> None:
    plan = plan_for(bootstrap)
    path = config.settings.fixtures_dir / "synthetic/product/new.v1.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(CheckpointError, match="STORY_INPUT_IDENTITY_CHANGED"):
        story_pass(plan, tmp_path / "added", execute=True)
    assert not (tmp_path / "added").exists()


def test_planned_root_is_bound_even_if_global_root_changes(bootstrap: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan = plan_for(bootstrap)
    monkeypatch.setattr(config, "settings", replace(config.settings, fixtures_dir=tmp_path / "wrong-root"))
    report = story_pass(plan, tmp_path / "fallback", mode="fallback", execute=True)
    assert report.receipts[0].admission == "ADMITTED"
    assert report.receipts[0].run_status == "WAITING_EVIDENCE"
    assert config.settings.fixtures_dir == tmp_path / "wrong-root"


def test_unexpected_rejection_is_not_recorded(bootstrap: Path, tmp_path: Path) -> None:
    plan = plan_for(bootstrap)
    plan.items[0].event.resource.id = "missing-case"
    report = story_pass(plan, tmp_path / "absent", mode="replay", execute=True)
    assert not report.complete and report.not_recorded == ["generated"]
    assert report.receipts[0].status == "ADMISSION_REJECTED"
    assert report.receipts[0].admission_reason == "Resource does not match a case"


def test_intentional_producer_denial_is_a_completed_no_call_action(bootstrap: Path, tmp_path: Path) -> None:
    plan = plan_for(bootstrap)
    plan.items[0].event.producer = "untrusted-test-producer"
    report = story_pass(plan, tmp_path / "absent", mode="replay", execute=True)
    assert report.complete and report.receipts[0].status == "REJECTED"
    assert report.receipts[0].model_calls == report.network_calls == 0


def test_recovered_retry_remains_complete_and_counts_both_attempts(bootstrap: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []
    def provider(**request: object) -> Response:
        calls.append(request)
        if len(calls) == 1:
            raise APIStatusError("retry", response=httpx.Response(429, request=httpx.Request("POST", "https://provider.invalid")), body=None)
        return provider_response(request)
    monkeypatch.setattr(client, "_call_api", provider)
    report = story_pass(plan_for(bootstrap), tmp_path / "retry", execute=True)
    assert report.complete and report.network_calls == len(calls) == 2
    assert report.receipts[0].model_calls == 2 and report.receipts[0].stop_reasons == []


def test_source_update_event_replays_from_same_base(bootstrap: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = config.settings.fixtures_dir / "synthetic/product/listing.v1.json"
    updated = json.loads(source.read_text(encoding="utf-8"))
    updated["version"] = 2
    updated["passages"][0]["text"] = "The revised capacity is 38 ml."
    update_path = source.with_name("listing.v2.json")
    update_path.write_text(json.dumps(updated), encoding="utf-8")
    plan = plan_for(bootstrap)
    event = plan.items[0].event.model_dump(mode="json")
    event.update(event_id="source-revision", idempotency_key="source-revision", type="SOURCE_CHANGED",
                 resource={"kind": "SOURCE", "id": updated["source_id"], "version": 2},
                 changed_fields=["volume"], payload={"case_id": "generated-case", "snapshot": "synthetic/product/listing.v2.json"})
    from app.models import EventEnvelope
    plan.items.append(StoryItem(name="source-update", event=EventEnvelope.model_validate(event)))
    calls: list[dict[str, object]] = []
    def provider(**request: object) -> Response:
        calls.append(request)
        return provider_response(request)
    monkeypatch.setattr(client, "_call_api", provider)
    output = tmp_path / "changed-story"
    recorded = story_pass(plan, output, execute=True)
    assert recorded.complete and recorded.network_calls == len(calls) == 2
    replayed = story_pass(plan, output, mode="replay", execute=True)
    assert replayed.complete and replayed.replay_equal and len(calls) == 2
    assert [receipt.model_calls for receipt in replayed.receipts] == [1, 1]


def test_missing_replay_after_successful_record_is_reported(bootstrap: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client, "_call_api", lambda **request: provider_response(request))
    output = tmp_path / "missing-recording"
    plan = plan_for(bootstrap)
    assert story_pass(plan, output, execute=True).complete
    recording = next((output / "replay").rglob("*.json"))
    recording.unlink()  # Only a generated temp recording, never a shared fixture.
    monkeypatch.setattr(client, "_call_api", lambda **kw: pytest.fail("Replay called provider"))
    result = story_pass(plan, output, mode="replay", execute=True)
    assert result.replay_equal is False and not result.complete
    assert result.network_calls == 0 and result.not_recorded == ["generated"]
