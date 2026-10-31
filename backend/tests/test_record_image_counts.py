"""Exact image token preflight, immutable identity and shared reservation caps."""
from dataclasses import replace
import hashlib
from pathlib import Path
import sys

from PIL import Image
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import config
from app.budget import Budget, BudgetExceeded
from app.llm import client
from app.llm.messages import ImagePart, build_input
from app.pipeline.extract import label_image
from scripts.record_all import PassLedger, PriceBook, ROOT, StoryPlan, image_count_key, prepare_image_counts
from scripts.smoke import TokenUsage, request_bound
from test_replay_pass import bootstrap
from test_replay_checkpoint import listing, provider_response
from test_record_story import plan_for
from scripts.record_all import story_pass


@pytest.fixture
def prices() -> PriceBook:
    return PriceBook.model_validate_json((ROOT / "backend/app/data/model_prices.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("dimensions", [(37, 83), (161, 49)])
def test_preflight_counts_canonical_images_once_and_reserves_generation(
    dimensions: tuple[int, int], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, prices: PriceBook,
) -> None:
    monkeypatch.setattr(config, "settings", replace(config.settings, llm_mode="record", replay_freeze=False,
                        llm_vision=True, model_extract="gpt-6.1-sol"))
    paths = [tmp_path / "one.png", tmp_path / "same.png"]
    for path in paths:
        Image.new("RGB", dimensions, "gray").save(path)
    plan = StoryPlan(fixtures_dir=tmp_path, max_calls=2, max_usd=2,
                     input_hashes={path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths})
    calls: list[float] = []
    def counter(*, model: str, image: ImagePart, timeout: float) -> int:
        assert model == "gpt-6.1-sol" and image == label_image(paths[0])
        calls.append(timeout)
        return 1203
    monkeypatch.setattr(client, "_call_token_count", counter)
    ledger = PassLedger(tmp_path / "ledger.jsonl", prices, max_calls=2)
    prepare_image_counts(plan, tmp_path, ledger)
    assert len(calls) == 1 and 0 < calls[0] <= config.settings.run_deadline_s
    assert ledger.state.calls == 1 and ledger.state.committed_usd == 0
    assert (tmp_path / "image-counts.json").is_file()
    messages = build_input("Extract claims.", [label_image(paths[0])])
    request = {"model": "gpt-6.1-sol", "input": messages, "max_output_tokens": 90}
    original_url = messages[1]["content"][0]["image_url"]
    sanitized, image_tokens = ledger._image_bound(request)
    ledger.reserve(request)
    assert image_tokens == 1203 and messages[1]["content"][0]["image_url"] == original_url
    assert ledger.state.committed_usd == prices.cost("gpt-6.1-sol", TokenUsage(
        input_tokens=request_bound(sanitized) + 1203, output_tokens=90))
    assert PassLedger(ledger.path, prices, max_calls=2).state == ledger.state
    with pytest.raises(BudgetExceeded, match="RECORD_PASS_CAP"):
        ledger.reserve_token_count()
    assert len(calls) == 1
    resumed = tmp_path / "resumed"
    resumed.mkdir()
    second = PassLedger(resumed / "ledger", prices)
    prepare_image_counts(plan, resumed, second, tmp_path / "image-counts.json")
    assert len(calls) == 1 and second.state.calls == 0
    assert second.image_counts == ledger.image_counts


@pytest.mark.parametrize("change", ["model", "detail", "image_url"])
def test_token_count_identity_binds_model_detail_and_content(change: str, tmp_path: Path, prices: PriceBook) -> None:
    part = {"type": "input_image", "image_url": "data:image/png;base64,first", "detail": "high"}
    ledger = PassLedger(tmp_path / "ledger", prices)
    ledger.image_counts[image_count_key("gpt-6.1-sol", part)] = 55
    altered = dict(part)
    model = "gpt-6.1-sol"
    if change == "model":
        model = "different-model"
    else:
        altered[change] = "different"
    with pytest.raises(BudgetExceeded, match="VISION_TOKEN_COST_NOT_VERIFIED"):
        ledger.reserve({"model": model, "input": [{"content": [altered]}], "max_output_tokens": 20})
    assert ledger.state.calls == 0


@pytest.mark.parametrize("freeze,mode", [(True, "record"), (False, "replay"), (False, "fallback")])
def test_image_count_freeze_and_offline_modes_deny_endpoint(freeze: bool, mode: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "settings", replace(config.settings, replay_freeze=freeze, llm_mode=mode))
    monkeypatch.setattr(client, "_call_token_count", lambda **kwargs: pytest.fail("offline count endpoint called"))
    budget = Budget()
    with pytest.raises(client.LLMError, match="TOKEN_COUNT_REQUIRES_RECORD_OR_LIVE"):
        client.count_image_tokens(model="gpt-6.1-sol", image=ImagePart(b"unused"), budget=budget)
    assert budget.tool_calls == 0


@pytest.mark.parametrize("count", [0, -1, True])
def test_invalid_exact_counts_fail_closed(count: int, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "settings", replace(config.settings, replay_freeze=False, llm_mode="record"))
    monkeypatch.setattr(client, "_call_token_count", lambda **kwargs: count)
    budget = Budget()
    with pytest.raises(client.LLMError, match="INVALID_TOKEN_COUNT"):
        client.count_image_tokens(model="gpt-6.1-sol", image=ImagePart(b"unused"), budget=budget)
    assert budget.tool_calls == 1


def test_story_record_preflight_overrides_ambient_fallback_and_replay_never_counts(
    bootstrap: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "settings", replace(config.settings, llm_mode="fallback", replay_freeze=False))
    image = config.settings.fixtures_dir / "synthetic/product/extra.png"
    Image.new("RGB", (71, 39), "gray").save(image)
    plan = plan_for(bootstrap)
    counts: list[str] = []
    def counter(**kwargs: object) -> int:
        counts.append(config.settings.llm_mode)
        return 271
    monkeypatch.setattr(client, "_call_token_count", counter)
    monkeypatch.setattr(client, "_call_api", lambda **request: provider_response(request))
    output = tmp_path / "record"
    recorded = story_pass(plan, output, execute=True, count_images=True)
    assert recorded.complete and counts == ["record"]
    assert config.settings.llm_mode == "fallback"
    replayed = story_pass(plan, output, mode="replay", execute=True, count_images=True)
    assert replayed.complete and replayed.network_calls == 0 and counts == ["record"]


def test_failed_count_retains_attempt_and_prevents_generation(
    bootstrap: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, prices: PriceBook,
) -> None:
    from openai import APIConnectionError
    import httpx2

    monkeypatch.setattr(config, "settings", replace(config.settings, replay_freeze=False))
    image = config.settings.fixtures_dir / "synthetic/product/extra.png"
    Image.new("RGB", (53, 57), "gray").save(image)
    def fail(**kwargs: object) -> int:
        raise APIConnectionError(request=httpx2.Request("POST", "https://api.openai.com/v1/responses/input_tokens"))
    monkeypatch.setattr(client, "_call_token_count", fail)
    monkeypatch.setattr(client, "_call_api", lambda **kwargs: pytest.fail("generation after failed count"))
    output = tmp_path / "failed-count"
    with pytest.raises(client.LLMError, match="TOKEN_COUNT_FAILED"):
        story_pass(plan_for(bootstrap), output, execute=True, count_images=True)
    assert PassLedger(output / "ledger.jsonl", prices).state.calls == 1
    assert not (output / "replay").exists()


def test_new_story_attempt_reuses_existing_recordings_without_generation(
    bootstrap: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(client, "_call_api", lambda **request: provider_response(request))
    plan = plan_for(bootstrap)
    original = tmp_path / "original"
    assert story_pass(plan, original, execute=True).complete
    entries = {path.relative_to(original / "replay"): path.read_bytes()
               for path in (original / "replay").rglob("*.json")}
    monkeypatch.setattr(client, "_call_api", lambda **kwargs: pytest.fail("duplicate generation"))
    continued = tmp_path / "continued"
    result = story_pass(plan, continued, execute=True, replay_dir=original / "replay")
    assert result.complete and result.network_calls == 0 and result.reserved_usd == 0
    assert entries == {path.relative_to(original / "replay"): path.read_bytes()
                       for path in (original / "replay").rglob("*.json")}
    assert entries == {path.relative_to(continued / "replay"): path.read_bytes()
                       for path in (continued / "replay").rglob("*.json")}
