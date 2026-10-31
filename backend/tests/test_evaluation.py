"""P4 diagnostic boundaries, independent baselines and immutable report evidence."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sys
import subprocess

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from app import config
from app.models import EventOutcome, Readability, SourceKind, Verdict
from app.pipeline.baseline import BaselineClaim, compare_claims
from scripts import eval as evaluator


def claim(kind: SourceKind, field: str, value: str) -> BaselineClaim:
    return BaselineClaim(kind, field, value, {})


@pytest.mark.parametrize("listing,reference", [("85ml", "0.085 L"), ("17 g", "17g"), ("260 ml", "260 mL")])
def test_baseline_reuses_units_and_is_order_independent(listing: str, reference: str) -> None:
    claims = [claim(SourceKind.LISTING, "volume", listing), claim(SourceKind.BRAND_PAGE, "volume", reference)]
    before = repr(claims)
    forward = compare_claims(claims)
    assert forward == compare_claims(list(reversed(claims)))
    assert next(field for field in forward if field.field_key == "volume").verdict == Verdict.CONSISTENT
    assert repr(claims) == before


def test_baseline_deliberately_ignores_packaging_and_source_self_conflict() -> None:
    claims = [claim(SourceKind.LISTING, "volume", "85ml"),
              claim(SourceKind.BRAND_PAGE, "volume", "100ml"),
              claim(SourceKind.PACKAGING_IMAGE, "volume", "85ml")]
    result = {field.field_key: field for field in compare_claims(claims)}
    assert result["volume"].verdict == Verdict.CONFLICTING
    assert result["volume"].seller_attributable
    same_source = [claim(SourceKind.BRAND_PAGE, "skin_type", "dry skin"),
                   claim(SourceKind.BRAND_PAGE, "skin_type", "oily skin")]
    assert next(field for field in compare_claims(same_source) if field.field_key == "skin_type").verdict == Verdict.SINGLE_SOURCE


def test_baseline_unreadable_null_empty_and_unknown_are_not_support() -> None:
    readable = claim(SourceKind.LISTING, "volume", "92ml")
    unreadable = replace(readable, readability=Readability.UNREADABLE)
    null = replace(readable, raw_value=None)
    empty = BaselineClaim(SourceKind.LISTING, "key_ingredients", None, {"value": []})
    assert all(field.verdict == Verdict.INSUFFICIENT for field in compare_claims([unreadable, null, empty]))


def test_baseline_ingredient_inci_support_remains_directional() -> None:
    claims = [claim(SourceKind.LISTING, "key_ingredients", "Niacinamide"),
              claim(SourceKind.BRAND_PAGE, "inci_list", "Water, Niacinamide")]
    assert next(f for f in compare_claims(claims) if f.field_key == "key_ingredients").verdict == Verdict.CONSISTENT


def test_score_counts_missing_outputs_and_attribution_without_inventing_gold() -> None:
    fields = [evaluator.FieldComparison(field_key="volume", expected="CONSISTENT", b0="CONFLICTING",
        candidate=None, b0_seller_attributable=True, candidate_seller_attributable=None,
        expected_seller_attributable=False),
        evaluator.FieldComparison(field_key="skin_type", expected="UNCERTAIN", b0="INSUFFICIENT",
        candidate="UNCERTAIN", b0_seller_attributable=False, candidate_seller_attributable=False,
        expected_seller_attributable=False)]
    b0, candidate = evaluator.score_fields(fields, "B0"), evaluator.score_fields(fields, "candidate")
    assert b0.total == candidate.total == 2
    assert b0.correct == 0 and candidate.correct == 1
    assert b0.false_blame == 1 and candidate.false_blame == 0
    assert b0.correct_abstentions == candidate.correct_abstentions == 1
    assert candidate.abstentions == 1  # Missing output is not an abstention.
    checkpoint = evaluator.GoldCheckpoint(after_event="arbitrary", product_id="p", case_id="c",
        expected={"volume": "CONFLICTING"})
    assert evaluator.expected_attribution(checkpoint, "volume") is None
    checkpoint.invariants = {"volume": {"seller_attributable": False}}
    assert evaluator.expected_attribution(checkpoint, "volume") is False


@pytest.mark.parametrize("fault", ["reviewer", "order", "duplicate", "field"])
def test_gold_rejects_mislabelled_review_or_invalid_order(fault: str) -> None:
    payload = {"status": "DRAFT", "labelled_by": "draft:codex", "event_order": ["custom-event"],
        "checkpoints": [{"after_event": "custom-event", "product_id": "other", "case_id": "case",
                         "expected": {"volume": "CONSISTENT"}}]}
    if fault == "reviewer":
        payload["status"] = "REVIEWED"
    elif fault == "order":
        payload["event_order"] = ["different-event"]
    elif fault == "duplicate":
        payload["checkpoints"] *= 2
    else:
        payload["checkpoints"][0]["expected"] = {"unknown-field": "CONSISTENT"}
    with pytest.raises(ValidationError):
        evaluator.GoldFile.model_validate(payload)


def test_evaluation_preserves_gold_separates_review_status_and_does_not_recount_noop(tmp_path: Path) -> None:
    gold_path = ROOT / "fixtures/gold/dev/demo-story.json"
    raw = gold_path.read_bytes()
    gold = evaluator.GoldFile.model_validate_json(raw)
    # Reviewer annotation is synthetic test input, never written back to fixture gold.
    gold.checkpoints[1].status = "REVIEWED"
    gold.checkpoints[1].reviewed_by = "Test reviewer"
    original_database = config.settings.db_path
    report = evaluator.run_evaluation(gold, hashlib.sha256(raw).hexdigest(), "fallback", 2)
    assert report.totals["DRAFT"]["candidate"].total == 5
    assert report.totals["REVIEWED"]["candidate"].total == 5
    assert report.checkpoints[0].run_ids
    assert report.checkpoints[1].run_ids == []
    assert report.checkpoints[1].usage == evaluator.Usage()
    assert config.settings.db_path == original_database
    assert gold_path.read_bytes() == raw
    evaluator.write_report(report, tmp_path)
    first_archive = next(tmp_path.glob("eval-2*.json"))
    first_bytes = first_archive.read_bytes()
    evaluator.write_report(report, tmp_path)
    assert len(list(tmp_path.glob("eval-2*.json"))) == 2
    assert first_archive.read_bytes() == first_bytes
    assert "REVIEWED" in (tmp_path / "eval-latest.md").read_text(encoding="utf-8")


def test_usage_schema_matches_actual_budget_keys() -> None:
    usage = evaluator.StoredUsage.model_validate({"model_calls": {"used": 3, "cap": 9},
        "seconds": {"used": 1.25, "cap": 20},
        "tokens": {"input_tokens": 321, "output_tokens": 47, "reasoning_tokens": 12}})
    assert usage.model_calls.used == 3
    assert usage.tokens.input_tokens == 321 and usage.tokens.output_tokens == 47
    assert usage.seconds.used * 1000 == 1250


def test_console_supports_unicode_under_windows_legacy_encoding(tmp_path: Path) -> None:
    gold = json.loads((ROOT / "fixtures/gold/dev/demo-story.json").read_text(encoding="utf-8"))
    gold["checkpoints"] = gold["checkpoints"][:1]
    gold["event_order"] = gold["event_order"][:1]
    gold["checkpoints"][0]["preconditions"] = ["Nguồn thử nghiệm — dữ liệu đa ngôn ngữ 日本語"]
    source = tmp_path / "gold.json"
    source.write_text(json.dumps(gold, ensure_ascii=False), encoding="utf-8")
    result = subprocess.run([sys.executable, str(ROOT / "scripts/eval.py"), "--mode", "fallback",
        "--gold", str(source), "--output-dir", str(tmp_path / "out")], cwd=ROOT,
        env={**os.environ, "PYTHONIOENCODING": "cp1252"}, capture_output=True, check=False, timeout=15)
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    assert "日本語" in result.stdout.decode("utf-8")
    assert "Nguồn thử nghiệm" in (tmp_path / "out/eval-latest.md").read_text(encoding="utf-8")


def test_replay_miss_restarts_labelled_fallback_and_preserves_attempt(tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("REPLAY_DIR", str(tmp_path / "empty-replay"))
    monkeypatch.setenv("MODEL_EXTRACT", "offline-unrecorded-model")
    monkeypatch.setenv("REPLAY_FREEZE", "1")
    config.reload_settings()
    try:
        assert evaluator.main(["--mode", "replay", "--limit-checkpoints", "2", "--output-dir", str(tmp_path / "out")]) == 0
        report = evaluator.EvaluationReport.model_validate_json((tmp_path / "out/eval-latest.json").read_bytes())
        assert report.mode == "fallback" and report.requested_mode == "replay"
        assert report.fallback_reason and "REPLAY_MISS" in report.fallback_reason
        assert report.previous_attempt is not None and report.previous_attempt.mode == "replay"
        assert report.previous_attempt.checkpoints[0].stop_reasons == ["REPLAY_MISS"]
        assert len(report.checkpoints) == 2 and report.checkpoints[0].outcome == "ADMITTED"
        assert report.usage.model_calls == 0
        assert os.environ["REPLAY_FREEZE"] == "1"
        assert config.settings.replay_freeze is True
        assert "FALLBACK:" in capsys.readouterr().out
        assert not (tmp_path / "empty-replay").exists()
    finally:
        # monkeypatch restores env after test; reload once inside that restoration too.
        monkeypatch.undo()
        config.reload_settings()


@pytest.mark.parametrize("mode", ["live", "record"])
def test_eval_refuses_paid_modes_before_creating_report(mode: str, tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", mode)
    with pytest.raises(SystemExit) as error:
        evaluator.main(["--output-dir", str(tmp_path / "report")])
    assert error.value.code == 2 and not (tmp_path / "report").exists()


def test_settings_restore_freeze_on_exception(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.sync_check import isolated_settings
    with monkeypatch.context() as environment:
        environment.setenv("REPLAY_FREEZE", "1")
        config.reload_settings()
        with pytest.raises(ValueError, match="interrupted"):
            with isolated_settings("fallback", tmp_path / "unused.db", replay_freeze=False):
                assert not config.settings.replay_freeze
                raise ValueError("interrupted")
        assert os.environ["REPLAY_FREEZE"] == "1" and config.settings.replay_freeze is True
    config.reload_settings()


def test_unexpected_admission_outcome_is_execution_error_and_not_gold_rewrite() -> None:
    raw = (ROOT / "fixtures/gold/dev/demo-story.json").read_bytes()
    gold = evaluator.GoldFile.model_validate_json(raw)
    # Deliberately inconsistent test input; validates the diagnostic, not product policy.
    gold.checkpoints[0].outcome = EventOutcome.REJECTED
    report = evaluator.run_evaluation(gold, hashlib.sha256(raw).hexdigest(), "fallback", 1)
    assert report.checkpoints[0].outcome == "ADMITTED"
    assert report.checkpoints[0].error == "event outcome ADMITTED, expected REJECTED"
    assert report.checkpoints[0].expected_outcome == "REJECTED"
    assert (ROOT / "fixtures/gold/dev/demo-story.json").read_bytes() == raw


def test_provenance_includes_auxiliary_steps_and_deduplicates() -> None:
    run = evaluator.StoredRun(id="run", status="COMPLETED", stop_reason=None, model="extract-model",
        prompt_version="extract-v7", policy_version="policy-v3", usage_json=None)
    steps = [evaluator.TraceProvenance(model="audit-model", prompt_version="audit-v2"),
             evaluator.TraceProvenance(model="extract-model", prompt_version="extract-v7"),
             evaluator.TraceProvenance(prompt_version="retry-v4")]
    assert evaluator.model_metadata([run], steps) == (
        ["audit-model", "extract-model"], ["audit-v2", "extract-v7", "retry-v4"])
