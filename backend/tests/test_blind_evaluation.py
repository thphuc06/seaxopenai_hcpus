"""P4 blind evaluation: evidence fixed before execution and immutable first results."""
import json
from pathlib import Path
import sys

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app import config
from app.budget import BudgetExceeded
from app.llm import client as gateway
from app.models import PUBLIC_FIELDS
from scripts import blind_eval as blind


def sample_set(root: Path, quantity: str = "137 ml") -> tuple[Path, blind.BlindSet]:
    folder = root / "fixtures/blind/sample"
    folder.mkdir(parents=True)
    product = dict(product_id="sample-product", case_id="sample-case", name="Different sample lotion", brand="Example Lab",
        variant=quantity, market="VN", dataset_origin="SYNTHETIC", tenant_id="sample-tenant", listing_id="sample-listing")
    snapshot = dict(source_id="sample-source", product_id=product["product_id"], version=1, kind="LISTING",
        uri="synthetic://sample", captured_at="2026-10-31T03:00:00Z", dataset_origin="SYNTHETIC", visibility="PUBLIC",
        family="seller:sample", scope=dict(product=product["product_id"], variant=quantity, market="VN", version="1"),
        passages=[dict(id="sample-passage", locator="title", section="overview", text="Dung tích: " + quantity)])
    for name, value in (("product.json", product), ("listing.v1.json", snapshot)):
        (folder / name).write_text(json.dumps(value), encoding="utf-8")
    plan = root / "plan.json"
    plan.write_text('{"status":"DRAFT"}', encoding="utf-8")
    case = blind.BlindCase(product_id=product["product_id"], case_id=product["case_id"], folder="fixtures/blind/sample",
        status="DRAFT", expected={key: "SINGLE_SOURCE" if key == "volume" else "INSUFFICIENT" for key in PUBLIC_FIELDS},
        evidence={"volume": [dict(file="listing.v1.json", locator="title", excerpt=quantity)]},
        rationale={}, categories=["units"], claims=[], probes=[])
    dataset = blind.BlindSet(set_number=7, original_plan="plan.json", labelled_by="draft:test",
        cases=[case], deferred=[], limitations=["Test-only labels."])
    manifest = root / "manifest.json"
    manifest.write_text(dataset.model_dump_json(), encoding="utf-8")
    return manifest, dataset


@pytest.mark.parametrize("quantity", ["137 ml", "0.212 L"])
def test_first_report_frozen_inputs_and_settings_survive_rerun(tmp_path: Path, quantity: str) -> None:
    manifest, dataset = sample_set(tmp_path, quantity)
    path = tmp_path / "freeze.json"
    frozen = blind.freeze_inputs(tmp_path, manifest, dataset, path)
    before = {name: (tmp_path / name).read_bytes() for name in frozen.hashes}
    settings_before = config.settings.db_path, config.settings.fixtures_dir
    report = blind.run_set(dataset, frozen, "fallback", 0, root=tmp_path)
    assert all(result.error is None for result in report.results)
    assert report.totals["DRAFT"]["candidate"].correct == 5
    assert report.totals["REVIEWED"]["candidate"].total == 0
    assert report.usage.model_calls == 0
    assert (config.settings.db_path, config.settings.fixtures_dir) == settings_before
    blind.write_report(report, tmp_path / "reports")
    first = tmp_path / "reports/blind-set7.json"
    initial = first.read_bytes()
    report.run_id = "new-attempt"
    blind.write_report(report, tmp_path / "reports")
    assert first.read_bytes() == initial
    assert (tmp_path / "reports/blind-set7-rerun-new-attempt.json").exists()
    assert {name: (tmp_path / name).read_bytes() for name in frozen.hashes} == before
    assert blind.verify_freeze(tmp_path, manifest, dataset, path) == frozen


@pytest.mark.parametrize("change", ["source", "gold", "manifest"])
def test_changed_inputs_refuse_execution_without_replacing_freeze(tmp_path: Path, change: str) -> None:
    manifest, dataset = sample_set(tmp_path)
    path = tmp_path / "freeze.json"
    blind.freeze_inputs(tmp_path, manifest, dataset, path)
    before = path.read_bytes()
    selected = {"source": tmp_path / "fixtures/blind/sample/listing.v1.json", "gold": tmp_path / "plan.json", "manifest": manifest}[change]
    with selected.open("a", encoding="utf-8") as stream:
        stream.write("\n ")
    with pytest.raises(ValueError, match="Frozen inputs changed"):
        blind.verify_freeze(tmp_path, manifest, dataset, path)
    assert path.read_bytes() == before


def test_review_and_locator_checks_are_not_candidate_dependent(tmp_path: Path) -> None:
    manifest, dataset = sample_set(tmp_path)
    payload = dataset.cases[0].model_dump()
    payload["status"] = "REVIEWED"
    with pytest.raises(ValidationError, match="human reviewer"):
        blind.BlindCase.model_validate(payload)
    dataset.cases[0].evidence["volume"][0].excerpt = "not in source"
    with pytest.raises(ValueError, match="locator/excerpt"):
        blind.validate_inputs(tmp_path, manifest, dataset)
    with pytest.raises(ValueError, match="escapes"):
        blind.contained(tmp_path, "../outside.json")


def test_zero_record_cap_never_calls_provider_and_preserves_error(tmp_path: Path) -> None:
    manifest, dataset = sample_set(tmp_path)
    frozen = blind.freeze_inputs(tmp_path, manifest, dataset, tmp_path / "freeze.json")
    report = blind.run_set(dataset, frozen, "record", 0, root=tmp_path)
    assert report.results[0].error == "SET_CALL_CAP"
    assert report.usage.model_calls == 0


def test_replay_error_is_not_a_successful_abstention(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest, dataset = sample_set(tmp_path)
    frozen = blind.freeze_inputs(tmp_path, manifest, dataset, tmp_path / "freeze.json")
    with monkeypatch.context() as env:
        env.setenv("MODEL_EXTRACT", "unrecorded-test-model")
        env.setenv("REPLAY_DIR", str(tmp_path / "empty"))
        config.reload_settings()
        report = blind.run_set(dataset, frozen, "replay", 2, root=tmp_path)
        assert report.results[0].error and "REPLAY_MISS" in report.results[0].error
        assert report.results[0].fields  # Keep raw failure findings for diagnosis.
        assert report.totals["DRAFT"]["candidate"].correct == 0
        assert report.totals["DRAFT"]["candidate"].correct_abstentions == 0
        assert report.results[0].scores == {}
    config.reload_settings()


def price_book() -> blind.PriceBook:
    return blind.PriceBook.model_validate({"checked_on": "2026-10-31", "source_url": "https://example.test/prices",
        "models": {"extract": {"input_per_million": 1, "output_per_million": 2, "source_url": "https://example.test/extract"},
                   "costly": {"input_per_million": 1000, "output_per_million": 1000, "source_url": "https://example.test/costly"}},
        "tools": {"web_search_per_call": 0.01, "search_context_token_limit": 1000}})


def test_record_reservation_checks_each_model_and_never_resets_on_failure() -> None:
    prices = price_book()
    with pytest.raises(ValueError, match="Unknown active model"):
        blind.BlindRecordBudget(prices, {"extract", "unknown-cheap"}, 2)
    budget = blind.BlindRecordBudget(prices, {"extract", "costly"}, 2)
    request = {"model": "costly", "input": [], "max_output_tokens": 10}
    with pytest.raises(BudgetExceeded, match="RECORD_SESSION_CAP"):
        budget.reserve(request)
    assert budget.calls == 0
    request["model"] = "extract"
    budget.reserve(request)
    budget.reserve(request)
    with pytest.raises(BudgetExceeded, match="RECORD_SESSION_CAP"):
        budget.reserve(request)
    assert budget.calls == 2 and budget.reserved_usd > 0
    budget.abort()
    with pytest.raises(BudgetExceeded, match="RECORD_ACCOUNTING_UNKNOWN"):
        budget.reserve(request)


@pytest.mark.parametrize("unknown_setting", ["MODEL_CHEAP", "MODEL_AGENT"])
def test_record_preflight_rejects_unpriced_auxiliary_model(monkeypatch: pytest.MonkeyPatch, unknown_setting: str) -> None:
    with monkeypatch.context() as env:
        env.setenv("MODEL_EXTRACT", "gpt-6.1-sol")
        env.setenv(unknown_setting, "unpriced-auxiliary")
        config.reload_settings()
        with pytest.raises(ValueError, match="Unknown active model"):
            blind.BlindRecordBudget.from_settings(1)
    config.reload_settings()


def test_record_crash_stops_shared_session_and_preserves_error_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest, dataset = sample_set(tmp_path)
    frozen = blind.freeze_inputs(tmp_path, manifest, dataset, tmp_path / "freeze.json")
    budget = blind.BlindRecordBudget(price_book(), {"extract"}, 3)
    calls: list[str] = []
    def provider(**request: object) -> None:
        calls.append(str(request["model"]))
        raise OSError("provider transport failure")
    with monkeypatch.context() as env:
        env.setenv("MODEL_EXTRACT", "extract")
        env.setenv("REPLAY_DIR", str(tmp_path / "replay"))
        env.setattr(gateway, "_call_api", provider)
        config.reload_settings()
        report = blind.run_set(dataset, frozen, "record", 3, root=tmp_path, record_budget=budget)
        assert report.accounting_complete is False and budget.aborted
        assert len(calls) == budget.calls == 1
        blind.write_report(report, tmp_path / "reports")
        retained = (tmp_path / "reports/blind-set7.json").read_bytes()
        later = blind.run_set(dataset, frozen, "record", 2, root=tmp_path, record_budget=budget)
        assert len(calls) == 1
        assert later.results[0].error
        assert (tmp_path / "reports/blind-set7.json").read_bytes() == retained
    config.reload_settings()
