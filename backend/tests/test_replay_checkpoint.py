"""Offline CLI checkpoint through real extraction/storage and the provider seam."""
from __future__ import annotations

from collections.abc import Iterator
import json
import io
from pathlib import Path
import sys
from xml.etree import ElementTree

from openai.types.responses import Response
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import config
from app.llm import client
from app.models import Readability
from app.pipeline.extract import Claim, Extraction
from app.pipeline.normalize import normalize
from scripts.record_all import CheckpointError, Stage, TokenUsage, checkpoint, main, values


@pytest.fixture
def listing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    with monkeypatch.context() as env:
        env.setenv("MODEL_EXTRACT", "gpt-6.1-sol")
        env.setenv("LLM_MAX_OUTPUT_TOKENS", "2000")
        env.setenv("REPLAY_FREEZE", "0")
        env.setenv("OPENAI_API_KEY", "provider-test-placeholder")
        config.reload_settings()
        path = tmp_path / "listing.json"
        path.write_text(json.dumps({"source_id": "generated-source", "product_id": "generated-product", "kind": "LISTING",
            "version": 1, "dataset_origin": "SYNTHETIC", "passages": [{"locator": "specs:volume", "section": "specs", "text": "Capacity 38 ml."}]}), encoding="utf-8")
        yield path
    config.reload_settings()


def provider_response(request: dict[str, object], *, incomplete: bool = False) -> Response:
    text = request["input"][1]["content"][0]["text"]
    sv_id = text.splitlines()[0].split("=", 1)[1]
    root = ElementTree.fromstring(text[text.index("<SOURCE_DATA>"):])
    passage = root.find("passage")
    assert passage is not None
    output = {"source_version_id": sv_id, "ignored_instructions_detected": False, "claims": [{
        "field_key": "volume", "raw_value": "38 ml", "quote": "38 ml", "passage_id": passage.attrib["id"],
        "readability": "READABLE", "proposed_skin_types": None, "proposed_ingredients": None, "proposed_volume_ml": None}]}
    return Response.model_validate({"id": "test-response", "object": "response", "created_at": 0, "model": "gpt-6.1-sol",
        "status": "incomplete" if incomplete else "completed", "incomplete_details": {"reason": "max_output_tokens"} if incomplete else None,
        "parallel_tool_calls": False, "tool_choice": "auto", "tools": [],
        "output": [{"type": "message", "id": "msg", "role": "assistant", "status": "completed",
                    "content": [{"type": "output_text", "text": json.dumps(output), "annotations": []}]}],
        "usage": {"input_tokens": 20, "output_tokens": 10, "total_tokens": 30,
                  "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0}, "output_tokens_details": {"reasoning_tokens": 3}}})


def test_dry_run_is_network_free_and_creates_no_attempt(listing: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(**request: object) -> Response:
        pytest.fail("Dry run must not call provider")
    monkeypatch.setattr(client, "_call_api", forbidden)
    output = tmp_path / "dry"
    previous = config.settings
    result = checkpoint(listing, output)
    assert not output.exists()
    assert 0 < result.estimated_upper_usd < 0.50
    assert result.stages == []
    assert config.settings is previous


def test_record_replay_fallback_and_completed_rerun(listing: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    def provider(**request: object) -> Response:
        calls.append(request)
        return provider_response(request)
    monkeypatch.setattr(client, "_call_api", provider)
    output = tmp_path / "completed"
    result = checkpoint(listing, output, execute=True)
    assert len(calls) == 1
    assert result.replay_equal and result.fallback_equal
    record, replay, fallback = result.stages
    assert [stage.model_calls for stage in result.stages] == [1, 1, 0]
    assert record.tokens.input_tokens == 20 and record.tokens.reasoning_tokens == 3
    assert record.estimated_usd == pytest.approx(0.00014)
    assert replay.tokens.input_tokens == replay.tokens.output_tokens == 0
    assert replay.extractor == "REPLAY" and fallback.extractor == "FALLBACK"
    assert (output / "checkpoint.db").exists()
    recordings = {path: path.read_bytes() for path in output.glob("replay/**/*.json")}
    assert len(recordings) == 1
    assert checkpoint(listing, output, execute=True) == result
    assert len(calls) == 1
    assert recordings == {path: path.read_bytes() for path in recordings}
    snapshot = json.loads(listing.read_text(encoding="utf-8"))
    snapshot["passages"][0]["text"] = "Capacity 41 ml."
    listing.write_text(json.dumps(snapshot), encoding="utf-8")
    with pytest.raises(CheckpointError, match="OUTPUT_IDENTITY_CHANGED"):
        checkpoint(listing, output, execute=True)
    assert len(calls) == 1


def test_interrupted_attempt_never_resets_spending(listing: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    def provider(**request: object) -> Response:
        calls.append(request)
        return provider_response(request, incomplete=True)
    monkeypatch.setattr(client, "_call_api", provider)
    output = tmp_path / "failed"
    with pytest.raises(client.LLMError, match="INCOMPLETE"):
        checkpoint(listing, output, execute=True)
    assert (output / "attempt.json").exists() and not (output / "report.json").exists()
    with pytest.raises(CheckpointError, match="OUTPUT_EXISTS"):
        checkpoint(listing, output, execute=True)
    assert len(calls) == 1


def test_cost_cap_blocks_before_network_or_attempt(listing: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MAX_OUTPUT_TOKENS", "100000")
    config.reload_settings()
    def forbidden(**request: object) -> Response:
        pytest.fail("Over-cap estimate must not call provider")
    monkeypatch.setattr(client, "_call_api", forbidden)
    output = tmp_path / "expensive"
    with pytest.raises(CheckpointError, match="ESTIMATE_EXCEEDS_CAP"):
        checkpoint(listing, output, execute=True)
    assert not output.exists()


def test_freeze_cannot_masquerade_as_live_record(listing: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPLAY_FREEZE", "1")
    config.reload_settings()
    with pytest.raises(CheckpointError, match="REPLAY_FREEZE_ENABLED"):
        checkpoint(listing, tmp_path / "frozen", execute=True)


def test_diagnostic_canonical_comparison_ignores_inci_presentation() -> None:
    results = []
    for raw in ("Water, Niacinamide", "water, NIACINAMIDE."):
        claim = Claim("id", "sv", "passage", "inci_list", raw, normalize("inci_list", raw), raw,
                      Readability.READABLE, "FALLBACK", "extract-v1", "seed")
        results.append(Extraction([claim], False, "FALLBACK", False))
    assert values(results[0]) == values(results[1])


def test_cli_prints_saved_unicode_report_on_windows_console(listing: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / "console"
    report = checkpoint(listing, output)
    report.stages.append(Stage(mode="fallback", extractor="FALLBACK", claims=1, model_calls=0,
                               tokens=TokenUsage(), estimated_usd=0, values=["ánh sáng"]))
    output.mkdir()
    (output / "report.json").write_text(report.model_dump_json(), encoding="utf-8")
    buffer = io.BytesIO()
    console = io.TextIOWrapper(buffer, encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", console)
    monkeypatch.setattr(sys, "argv", ["record_all.py", str(listing), "--output-dir", str(output), "--execute"])
    assert main() == 0
    console.flush()
    printed = json.loads(buffer.getvalue().decode("cp1252"))
    assert printed["stages"][0]["values"] == ["ánh sáng"]
