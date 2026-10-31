"""Offline failure, spending and replay tests for the Phase 0 probe."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from openai import AuthenticationError, PermissionDeniedError
from openai.types.responses import Response

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.smoke import (
    PriceBook, SmokeBudget, SmokeFailure, SmokeRunner, SmokeSettings, TokenUsage,
    check_complete, domain_matches, error_code, record_or_replay, replay_key,
)


@pytest.fixture
def prices() -> PriceBook:
    return PriceBook.model_validate_json((Path(__file__).parents[1] / "app/data/model_prices.json").read_text(encoding="utf-8"))


def response(*, status: str = "completed", output: list[dict[str, object]] | None = None) -> Response:
    return Response.model_validate({
        "id": "response-test", "object": "response", "created_at": 0,
        "model": "gpt-6.1-sol", "status": status, "output": output or [],
        "parallel_tool_calls": False, "tool_choice": "auto", "tools": [],
        "usage": {"input_tokens": 20, "output_tokens": 10, "total_tokens": 30,
                  "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                  "output_tokens_details": {"reasoning_tokens": 3}},
    })


def test_call_cap_blocks_sixteenth_request() -> None:
    budget = SmokeBudget()
    for _ in range(15):
        budget.reserve(0.001)
    with pytest.raises(SmokeFailure, match="SMOKE_CALL_CAP"):
        budget.reserve(0.001)
    assert budget.state.calls == 15


def test_money_cap_precedes_network_and_survives_restart(tmp_path: Path) -> None:
    path = tmp_path / "ledger.json"
    budget = SmokeBudget(path=path)
    budget.reserve(0.30)
    restarted = SmokeBudget(path=path)
    with pytest.raises(SmokeFailure, match="SMOKE_DOLLAR_CAP"):
        restarted.reserve(0.21)
    assert restarted.state.calls == 1
    assert restarted.state.committed_usd == pytest.approx(0.30)


def test_usage_settlement_releases_only_unused_reservation() -> None:
    budget = SmokeBudget()
    reservation = budget.reserve(0.20)
    budget.settle(reservation, 0.003)
    assert budget.state.calls == 1
    assert budget.state.committed_usd == pytest.approx(0.003)


@pytest.mark.parametrize("invalid", [-1.0, float("inf"), float("nan")])
def test_invalid_reservations_cannot_bypass_limit(invalid: float) -> None:
    budget = SmokeBudget()
    with pytest.raises(ValueError):
        budget.reserve(invalid)
    assert budget.state.calls == 0


def test_larger_than_reserved_cost_stops_and_is_retained() -> None:
    budget = SmokeBudget()
    reservation = budget.reserve(0.01)
    with pytest.raises(SmokeFailure, match="COST_ESTIMATE_EXCEEDED"):
        budget.settle(reservation, 0.02)
    assert budget.state.committed_usd == pytest.approx(0.02)


def test_reasoning_tokens_not_double_charged(prices: PriceBook) -> None:
    usage = TokenUsage(input_tokens=1000, output_tokens=2000, reasoning_tokens=1500)
    assert prices.cost("gpt-6.1-sol", usage) == pytest.approx(0.022)
    assert prices.cost("gpt-6.1-sol", usage, searches=1) == pytest.approx(0.032)


def test_unreviewed_model_fails_closed(prices: PriceBook) -> None:
    with pytest.raises(SmokeFailure, match="MODEL_PRICE_NOT_REVIEWED"):
        prices.cost("unpriced-model", TokenUsage(input_tokens=1))


def test_completed_response_is_accepted() -> None:
    check_complete(response())


@pytest.mark.parametrize("status", ["incomplete", "failed", "cancelled", "in_progress"])
def test_noncompleted_response_never_accepted(status: str) -> None:
    with pytest.raises(SmokeFailure):
        check_complete(response(status=status))


def test_refusal_is_not_success() -> None:
    result = response(output=[{"id": "msg", "type": "message", "role": "assistant", "status": "completed", "content": [{"type": "refusal", "refusal": "declined"}]}])
    with pytest.raises(SmokeFailure, match="REFUSAL"):
        check_complete(result)


@pytest.mark.parametrize("url,expected", [
    ("https://openai.com/a", True), ("https://docs.openai.com/a", True),
    ("https://openai.com.attacker.test/a", False), ("https://notopenai.com/a", False),
    ("https://openai.com@attacker.test/a", False), ("http://openai.com/a", False),
])
def test_domain_validation_checks_hostname_boundary(url: str, expected: bool) -> None:
    assert domain_matches(url, "openai.com") is expected


def test_replay_reuses_bytes_without_invoking_client(tmp_path: Path) -> None:
    calls: list[str] = []

    def call() -> str:
        calls.append("network")
        return '{"text":"Xin chào"}'

    identity = {"model": "model-a", "schema": {"field": "text"}, "input": ["source"], "step": "extract", "prompt_version": "v1"}
    first = record_or_replay(tmp_path, identity, call)
    second = record_or_replay(tmp_path, dict(reversed(list(identity.items()))), call)
    assert first == second
    assert calls == ["network"]
    assert len(list(tmp_path.iterdir())) == 1


@pytest.mark.parametrize("key,value", [
    ("model", "b"), ("step", "retry"), ("prompt_version", "v2"),
    ("instructions", "changed"), ("input", ["new image bytes"]),
    ("schema", {"new": "field"}), ("tools", [{"name": "different"}]),
])
def test_replay_identity_changes_for_every_model_visible_component(key: str, value: object) -> None:
    identity = {"model": "a", "step": "extract", "prompt_version": "v1", "instructions": "extract", "input": ["image bytes"], "schema": {"text": "str"}, "tools": []}
    assert replay_key(identity) != replay_key({**identity, key: value})


def test_raw_exception_text_does_not_escape() -> None:
    assert error_code(ValueError("credential-shaped-secret")) == "ValueError"


def test_failed_transport_keeps_reservation(prices: PriceBook) -> None:
    class BrokenResponses:
        def create(self, **request: object) -> Response:
            raise OSError("network interrupted")

    runner = SmokeRunner(SmokeSettings(), prices, SmokeBudget(), SimpleNamespace(responses=BrokenResponses()), SimpleNamespace())
    runner.row("1_text", runner.plain)
    assert runner.rows[0].status == "FAIL"
    assert runner.rows[0].detail == "OSError"
    assert runner.budget.state.calls == 1
    assert runner.budget.state.committed_usd > 0


def test_completed_request_is_metered_before_status_check(prices: PriceBook) -> None:
    class IncompleteResponses:
        def create(self, **request: object) -> Response:
            return response(status="incomplete")

    runner = SmokeRunner(SmokeSettings(), prices, SmokeBudget(), SimpleNamespace(responses=IncompleteResponses()), SimpleNamespace())
    runner.row("1_text", runner.plain)
    assert runner.rows[0].status == "FAIL"
    assert runner.rows[0].detail == "INCOMPLETE"
    assert runner.rows[0].usage.reasoning_tokens == 3
    assert runner.budget.state.committed_usd == pytest.approx(0.00014)


def test_real_agents_sdk_typed_tool_path_with_fake_provider(prices: PriceBook) -> None:
    class FakeResponses:
        def __init__(self) -> None:
            self.calls = 0

        async def create(self, **request: object) -> Response:
            self.calls += 1
            if self.calls == 1:
                return response(output=[{"type": "function_call", "id": "call-1", "call_id": "tool-1", "name": "add_numbers", "arguments": json.dumps({"a": 19, "b": 23}), "status": "completed"}])
            return response(output=[{"type": "message", "id": "msg-2", "role": "assistant", "status": "completed", "content": [{"type": "output_text", "text": '{"total":42}', "annotations": []}]}])

    provider = FakeResponses()
    runner = SmokeRunner(SmokeSettings(), prices, SmokeBudget(), SimpleNamespace(), SimpleNamespace(responses=provider, base_url="https://api.openai.com/v1"))
    try:
        detail = runner.agents()
    finally:
        runner.event_loop.close()
    assert "method=output_type" in detail
    assert provider.calls == 2
    assert runner.budget.state.calls == 2
    assert sum(usage.output_tokens for usage, _ in runner.samples) == 20


@pytest.mark.parametrize("error_type,status", [(AuthenticationError, 401), (PermissionDeniedError, 403)])
def test_account_access_failure_stops_all_remaining_requests(prices: PriceBook, error_type: type[Exception], status: int, capsys: pytest.CaptureFixture[str]) -> None:
    class DeniedResponses:
        calls = 0

        def create(self, **request: object) -> Response:
            self.calls += 1
            raise error_type("private credential must not be printed", response=SimpleNamespace(status_code=status, request=SimpleNamespace(), headers={}), body=None)

    provider = DeniedResponses()
    runner = SmokeRunner(SmokeSettings(), prices, SmokeBudget(), SimpleNamespace(responses=provider), SimpleNamespace())
    rows = runner.run()
    assert len(rows) == 8
    assert rows[0].status == "FAIL"
    assert all(row.status == "SKIP" and row.detail == "ACCOUNT_ACCESS_REQUIRED" for row in rows[1:])
    assert provider.calls == 1
    assert runner.budget.state.calls == 1
    assert "private credential" not in rows[0].detail
    printed = capsys.readouterr().out
    assert "2_structured: SKIP ACCOUNT_ACCESS_REQUIRED" in printed
    assert "private credential" not in printed


def test_exhausted_budget_stops_before_external_client(prices: PriceBook) -> None:
    budget = SmokeBudget()
    budget.reserve(0.50)
    runner = SmokeRunner(SmokeSettings(), prices, budget, SimpleNamespace(), SimpleNamespace())
    rows = runner.run()
    assert rows[0].detail == "SMOKE_DOLLAR_CAP"
    assert all(row.status == "SKIP" for row in rows[1:])
    assert budget.state.calls == 1


def test_agents_submit_alternative_is_typed_and_budgeted(prices: PriceBook) -> None:
    class FakeResponses:
        def __init__(self) -> None:
            self.calls = 0

        async def create(self, **request: object) -> Response:
            self.calls += 1
            if self.calls == 1:
                return response(output=[{"type": "message", "id": "bad-msg", "role": "assistant", "status": "completed", "content": [{"type": "output_text", "text": "invalid structured output", "annotations": []}]}])
            if self.calls == 2:
                name, arguments = "add_numbers", {"a": 19, "b": 23}
            else:
                name, arguments = "submit_result", {"result": {"total": 42}}
            return response(output=[{"type": "function_call", "id": f"call-{self.calls}", "call_id": f"tool-{self.calls}", "name": name, "arguments": json.dumps(arguments), "status": "completed"}])

    provider = FakeResponses()
    runner = SmokeRunner(SmokeSettings(), prices, SmokeBudget(), SimpleNamespace(), SimpleNamespace(responses=provider, base_url="https://api.openai.com/v1"))
    try:
        detail = runner.agents()
    finally:
        runner.event_loop.close()
    assert "method=submit_tool" in detail
    assert provider.calls == 3
    assert runner.budget.state.calls == 3
