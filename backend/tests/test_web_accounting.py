"""One durable ledger spans hosted search, HTTP and offline replay."""
import json
from pathlib import Path
import sys

import pytest
from openai.types.responses import Response

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import config, db
from app.budget import BudgetExceeded
from app.connectors import websearch
from app.context import RunContext
from app.llm import client
from scripts.record_all import PassLedger, PriceBook, ROOT, StoryReport, main, story_pass, story_plan
from scripts.smoke import TokenUsage, request_bound
from test_web import context
from test_web_provider import response, session
from test_replay_pass import bootstrap
from test_replay_checkpoint import listing
from test_record_story import plan_for


def prices() -> PriceBook:
    return PriceBook.model_validate_json((ROOT / "backend/app/data/model_prices.json").read_text(encoding="utf-8"))


def test_search_fetch_share_durable_cap_and_replay_spends_nothing(context: RunContext, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    context.mode = "record"
    monkeypatch.setenv("MODEL_AGENT", "gpt-6.1-sol")
    config.reload_settings()
    ledger = PassLedger(tmp_path / "ledger.jsonl", prices(), max_calls=2, max_usd=2)
    model_calls: list[dict[str, object]] = []
    fetches: list[str] = []
    def model(**request: object) -> Response:
        assert ledger.state.calls == 1 and ledger.path.is_file()
        model_calls.append(request)
        return response()
    def http(url: str, *, timeout: float) -> websearch.Page:
        assert ledger.state.calls == 2
        fetches.append(url)
        return websearch.Page(url=url, status=200, text="Aurora Meadow Gel. Capacity 38 ml.", fetched_at=db.now_iso())
    monkeypatch.setattr(client, "_call_api", model)
    monkeypatch.setattr(websearch, "_fetch_http", http)
    with client.network_guard(ledger.reserve):
        transport = session(context)
        result = transport.search("Aurora Meadow Gel")
        page = transport.fetch(result[0].url)
        with pytest.raises(BudgetExceeded, match="RECORD_PASS_CAP"):
            session(context).search("Aurora different query")
    assert len(model_calls) == len(fetches) == 1
    request = model_calls[0]
    expected = prices().cost("gpt-6.1-sol", TokenUsage(input_tokens=request_bound(request, web_tokens=128000),
                                                    output_tokens=request["max_output_tokens"]), searches=1)
    assert ledger.state.committed_usd == pytest.approx(expected)
    assert len(ledger.path.read_text(encoding="utf-8").splitlines()) == 2
    restored = PassLedger(ledger.path, prices(), max_calls=2, max_usd=2)
    context.mode = "replay"
    with client.network_guard(restored.reserve):
        replay = session(context)
        assert replay.search("Aurora Meadow Gel") == result
        assert replay.fetch(page.url) == page
    assert len(model_calls) == len(fetches) == 1 and restored.state.calls == 2
    assert context.budget.model_calls == 3 and context.budget.tool_calls == 5


@pytest.mark.parametrize("mutation", ["unbounded", "other_tool", "unlimited", "priority", "mixed"])
def test_unpriced_tool_shapes_are_rejected(tmp_path: Path, mutation: str) -> None:
    request = websearch.search_request("Brand source", ["brand.example"], "VN")
    if mutation == "unbounded":
        request.pop("max_tool_calls")
    elif mutation == "other_tool":
        request["tools"] = [{"type": "file_search"}]
    elif mutation == "unlimited":
        request["tools"][0]["return_token_budget"] = "unlimited"
    elif mutation == "priority":
        request["service_tier"] = "priority"
    else:
        request["tools"].append({"type": "web_search"})
    ledger = PassLedger(tmp_path / "ledger", prices())
    with pytest.raises(BudgetExceeded, match="REQUEST_COST_NOT_VERIFIED"):
        ledger.reserve(request)
    assert ledger.state.calls == 0 and not ledger.path.exists()


def test_dollar_cap_blocks_hosted_provider_and_fetch_failure_keeps_reservation(context: RunContext, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    context.mode = "record"
    ledger = PassLedger(tmp_path / "small", prices(), max_usd=0.001)
    with client.network_guard(ledger.reserve), pytest.raises(BudgetExceeded, match="RECORD_PASS_CAP"):
        session(context).search("Aurora query")
    assert ledger.state.calls == 0
    def failed_fetch(url: str) -> websearch.Page:
        raise websearch.WebError("HTTP_STATUS_503")
    monkeypatch.setattr(websearch, "fetch", failed_fetch)
    ledger = PassLedger(tmp_path / "http", prices(), max_calls=1)
    transport = session(context)
    url = "https://aurora.example/gel"
    transport.returned_urls.add(url)
    with client.network_guard(ledger.reserve), pytest.raises(websearch.WebError, match="HTTP_STATUS_503"):
        transport.fetch(url)
    assert ledger.state.calls == 1 and ledger.state.committed_usd == 0
    with client.network_guard(ledger.reserve), pytest.raises(BudgetExceeded, match="RECORD_PASS_CAP"):
        another = session(context)
        another.returned_urls.add(url)
        another.fetch(url)


def test_web_plan_is_explicit_frozen_and_missing_hook_is_incomplete(bootstrap: Path, tmp_path: Path) -> None:
    product = config.settings.fixtures_dir / "synthetic/product/product.json"
    payload = json.loads(product.read_text(encoding="utf-8"))
    payload["web"] = {"enabled": True, "brand_domains": ["brand.example"], "aliases": ["Sample"]}
    product.write_text(json.dumps(payload), encoding="utf-8")
    events = config.settings.fixtures_dir / "events"
    events.mkdir()
    (events / "01-bootstrap.json").write_text(bootstrap.read_text(encoding="utf-8"), encoding="utf-8")
    off, on = story_plan(), story_plan(web="on")
    assert off.web == "off" and on.web == "on" and off.fingerprint != on.fingerprint
    assert on.estimated_calls_upper > off.estimated_calls_upper
    plan = plan_for(bootstrap)
    plan.web = "on"
    report = story_pass(plan, tmp_path / "fallback", mode="fallback", execute=True)
    assert not report.complete and report.network_calls == 0
    assert "WEB_NOT_EXECUTED" in report.receipts[0].stop_reasons
    assert report.receipts[0].status == "PARTIAL" and report.not_recorded


def test_cli_web_dry_run_never_executes(bootstrap: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "argv", ["record_all.py", "--story", "--web", "on", "--dry-run",
                                    "--output-dir", str(tmp_path / "no-output")])
    monkeypatch.setattr(client, "_call_api", lambda **kwargs: pytest.fail("dry run provider"))
    assert main() == 1  # This small synthetic corpus intentionally lacks the full story.
    report = StoryReport.model_validate_json(capsys.readouterr().out.split("\n", 1)[1])
    assert report.dry_run and report.plan.web == "on" and report.network_calls == 0
    assert not (tmp_path / "no-output").exists()
