"""Offline gateway checks through the documented external-client seam."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import json
from pathlib import Path
from threading import Event

import httpx
from openai import APIConnectionError, APIStatusError
from openai.types.responses import Response
from pydantic import BaseModel, ConfigDict
import pytest

from app import config
from app.budget import Budget, BudgetExceeded
from app.context import RunContext
from app.llm import client
from app.llm.messages import ImagePart, TextPart


class Output(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    text: str


@dataclass
class Trace:
    rows: list[dict[str, object]] = field(default_factory=list)

    def step(self, step: str, **kwargs: object) -> None:
        self.rows.append({"step": step, **kwargs})


@pytest.fixture
def context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    with monkeypatch.context() as env:
        env.setenv("REPLAY_DIR", str(tmp_path / "recordings"))
        env.setenv("REPLAY_FREEZE", "0")
        config.reload_settings()
        yield RunContext("run", "case", "tenant", 1, {}, "record", Budget(), Trace())
    config.reload_settings()


def response(*, text: str = '{"text":"one"}', status: str = "completed", refusal: bool = False) -> Response:
    content = {"type": "refusal", "refusal": "declined"} if refusal else {"type": "output_text", "text": text, "annotations": []}
    return Response.model_validate({
        "id": "unit-response", "object": "response", "created_at": 0, "model": "unit-model", "status": status,
        "incomplete_details": {"reason": "max_output_tokens"} if status == "incomplete" else None,
        "output": [{"type": "message", "id": "message", "role": "assistant", "status": "completed", "content": [content]}],
        "parallel_tool_calls": False, "tool_choice": "auto", "tools": [],
        "usage": {"input_tokens": 20, "output_tokens": 10, "total_tokens": 30,
                  "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                  "output_tokens_details": {"reasoning_tokens": 3}},
    })


def call(context: RunContext, **overrides: object) -> client.LLMResult[Output]:
    request = dict(step="extract", model="unit-model", instructions="Extract source text.",
                   input_parts=[TextPart("<SOURCE_DATA>one</SOURCE_DATA>")], schema=Output,
                   ctx=context, prompt_version="unit-v1")
    return client.parse(**(request | overrides))


def test_record_hit_and_replay_are_immutable_and_budgeted(context: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    requests = []
    def provider(**request: object) -> Response:
        requests.append(request)
        return response()
    monkeypatch.setattr(client, "_call_api", provider)
    first = call(context)
    path = next(config.settings.replay_dir.rglob("*.json"))
    before = path.read_bytes(), path.stat().st_mtime_ns
    second = call(context)
    context.mode = "replay"
    third = call(context)
    assert first.parsed == second.parsed == third.parsed == Output(text="one")
    assert not first.replayed and second.replayed and third.replayed
    assert len(requests) == 1 and context.budget.model_calls == 3
    assert second.usage == {"input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0}
    assert context.budget.usage()["tokens"] == {"input_tokens": 20, "output_tokens": 10, "reasoning_tokens": 3}
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    assert 0 < requests[0]["timeout"] <= 120


def test_live_does_not_replace_recording(context: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client, "_call_api", lambda **kwargs: response())
    call(context)
    path = next(config.settings.replay_dir.rglob("*.json"))
    before = path.read_bytes()
    context.mode = "live"
    monkeypatch.setattr(client, "_call_api", lambda **kwargs: response(text='{"text":"two"}'))
    assert call(context).parsed.text == "two"
    assert path.read_bytes() == before
    call(context, prompt_version="new")
    assert len(list(config.settings.replay_dir.rglob("*.json"))) == 1


@pytest.mark.parametrize("mode", ["record", "live"])
def test_freeze_loads_or_misses_without_network(context: RunContext, monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    monkeypatch.setattr(client, "_call_api", lambda **kwargs: response())
    call(context)
    monkeypatch.setenv("REPLAY_FREEZE", "1")
    config.reload_settings()
    context.mode = mode
    def forbidden(**request: object) -> Response:
        pytest.fail("network must not run")
    monkeypatch.setattr(client, "_call_api", forbidden)
    assert call(context).replayed
    with pytest.raises(client.LLMError, match="REPLAY_MISS"):
        call(context, instructions="different")
    assert len(list(config.settings.replay_dir.rglob("*.json"))) == 1


@pytest.mark.parametrize("change", ["model", "step", "instructions", "prompt_version", "effort", "max_output_tokens", "text", "image", "detail", "schema"])
def test_record_key_covers_every_request_component(context: RunContext, monkeypatch: pytest.MonkeyPatch, change: str) -> None:
    monkeypatch.setattr(client, "_call_api", lambda **kwargs: response())
    png = b"\x89PNG\r\n\x1a\nbytes-one"
    base = {"input_parts": [TextPart("<SOURCE_DATA>one</SOURCE_DATA>"), ImagePart(png)]}
    call(context, **base)
    class Alternative(Output):
        pass
    variants = {"model": "other", "step": "extract:retry", "instructions": "other", "prompt_version": "v2",
                "effort": "medium", "max_output_tokens": 512, "schema": Alternative,
                "text": [TextPart("<SOURCE_DATA>two</SOURCE_DATA>"), ImagePart(png)],
                "image": [TextPart("<SOURCE_DATA>one</SOURCE_DATA>"), ImagePart(png + b"two")],
                "detail": [TextPart("<SOURCE_DATA>one</SOURCE_DATA>"), ImagePart(png, "low")]}
    key = "input_parts" if change in {"text", "image", "detail"} else change
    call(context, **(base | {key: variants[change]}))
    assert len(list(config.settings.replay_dir.rglob("*.json"))) == 2


@pytest.mark.parametrize("status,refusal,text,code", [
    ("incomplete", False, '{"text":"partial"}', "INCOMPLETE:max_output_tokens"),
    ("completed", True, "", "REFUSAL"), ("failed", False, "{}", "API_ERROR"),
    ("completed", False, '{"text":2}', "INVALID_OUTPUT"),
    ("completed", False, '{"text":"ok","extra":1}', "INVALID_OUTPUT"),
])
def test_bad_response_not_recorded(context: RunContext, monkeypatch: pytest.MonkeyPatch, status: str, refusal: bool, text: str, code: str) -> None:
    monkeypatch.setattr(client, "_call_api", lambda **kwargs: response(status=status, refusal=refusal, text=text))
    with pytest.raises(client.LLMError, match=code):
        call(context)
    assert not list(config.settings.replay_dir.rglob("*.json"))
    assert context.budget.model_calls == 1
    assert context.budget.usage()["tokens"]["output_tokens"] == 10
    assert context.trace.rows[-1]["error"]


@pytest.mark.parametrize("status,expected", [(429, 2), (500, 2), (503, 2), (401, 1), (400, 1)])
def test_only_transient_http_errors_retry_once(context: RunContext, monkeypatch: pytest.MonkeyPatch, status: int, expected: int) -> None:
    requests = []
    def provider(**request: object) -> Response:
        requests.append(request)
        if len(requests) == 1:
            raise APIStatusError("private provider payload", response=httpx.Response(status, request=httpx.Request("POST", "https://example.invalid")), body=None)
        return response()
    monkeypatch.setattr(client, "_call_api", provider)
    if expected == 2:
        assert call(context).parsed.text == "one"
    else:
        with pytest.raises(client.LLMError, match=f"HTTP_{status}"):
            call(context)
    assert len(requests) == context.budget.model_calls == expected
    assert "private provider payload" not in str(context.trace.rows)


def test_retry_cannot_exceed_budget(context: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    context.budget = Budget(max_model_calls=1)
    def provider(**request: object) -> Response:
        raise APIStatusError("busy", response=httpx.Response(429, request=httpx.Request("POST", "https://example.invalid")), body=None)
    monkeypatch.setattr(client, "_call_api", provider)
    with pytest.raises(BudgetExceeded, match="MODEL_CALL_LIMIT"):
        call(context)
    assert context.budget.model_calls == 1


def test_replay_validates_recorded_output(context: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client, "_call_api", lambda **kwargs: response())
    call(context)
    path = next(config.settings.replay_dir.rglob("*.json"))
    data = json.loads(path.read_text(encoding="utf-8"))
    data["output"] = {"text": 123}
    path.write_text(json.dumps(data), encoding="utf-8")
    context.mode = "replay"
    with pytest.raises(client.LLMError, match="INVALID_RECORDING"):
        call(context)


@pytest.mark.parametrize("mode", ["fallback", "replay"])
def test_no_implicit_network(context: RunContext, monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    context.mode = mode
    def forbidden(**request: object) -> Response:
        pytest.fail("unexpected network")
    monkeypatch.setattr(client, "_call_api", forbidden)
    with pytest.raises(client.LLMError, match="FALLBACK_MODE" if mode == "fallback" else "REPLAY_MISS"):
        call(context)
    assert context.budget.model_calls == (0 if mode == "fallback" else 1)


def test_async_adapter_works(context: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client, "_call_api", lambda **kwargs: response())
    result = asyncio.run(client.aparse(step="extract", model="unit-model", instructions="extract",
                         input_parts=[TextPart("<SOURCE_DATA>x</SOURCE_DATA>")], schema=Output, ctx=context, prompt_version="v1"))
    assert result.parsed.text == "one"


def test_expired_deadline_blocks_api_and_recording(context: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    now = [0.0]
    context.budget = Budget(deadline_s=2, _clock=lambda: now[0])
    def provider(**request: object) -> Response:
        now[0] = 3.0
        return response()
    monkeypatch.setattr(client, "_call_api", provider)
    with pytest.raises(BudgetExceeded, match="RUN_DEADLINE"):
        call(context)
    assert not list(config.settings.replay_dir.rglob("*.json"))
    assert context.budget.usage()["tokens"]["output_tokens"] == 10


@pytest.mark.parametrize("mode,deadline", [("live", 0.5), ("record", 7.0)])
def test_late_response_usage_is_traced_without_recording(
    context: RunContext, monkeypatch: pytest.MonkeyPatch, mode: str, deadline: float,
) -> None:
    now = [0.0]
    context.mode = mode
    context.budget = Budget(deadline_s=deadline, _clock=lambda: now[0])

    def provider(**request: object) -> Response:
        now[0] = deadline + 1.0
        return response(text='{"text":"different response"}')

    monkeypatch.setattr(client, "_call_api", provider)
    with pytest.raises(BudgetExceeded, match="RUN_DEADLINE"):
        call(context, step="agent:variant", prompt_version="deadline-variant")
    assert context.budget.model_calls == 1
    assert context.budget.usage()["tokens"] == {
        "input_tokens": 20, "output_tokens": 10, "reasoning_tokens": 3,
    }
    assert context.trace.rows[-1]["tokens_out"] == 10
    assert context.trace.rows[-1]["error"] == "RUN_DEADLINE"
    assert not list(config.settings.replay_dir.rglob("*.json"))


def test_connection_error_sanitized(context: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    def provider(**request: object) -> Response:
        raise APIConnectionError(message="private data", request=httpx.Request("POST", "https://example.invalid"))
    monkeypatch.setattr(client, "_call_api", provider)
    with pytest.raises(client.LLMError, match="^API_ERROR$"):
        call(context)
    assert context.budget.model_calls == 1


def test_sdk_raw_envelope_preserves_incomplete_with_truncated_json(context: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    class Raw:
        content = response(text='{"text":', status="incomplete").model_dump_json().encode()

        def parse(self) -> Response:
            pytest.fail("incomplete output must be inspected before SDK schema parsing")

    class Provider:
        def __init__(self, **kwargs: object) -> None:
            assert kwargs["max_retries"] == 0
            assert 0 < kwargs["timeout"] <= 120
            self.responses = self
            self.with_raw_response = self

        def __enter__(self) -> Provider:
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def parse(self, **request: object) -> Raw:
            assert request["text_format"] is Output
            return Raw()

    monkeypatch.setattr(client, "OpenAI", Provider)
    with pytest.raises(client.LLMError, match="INCOMPLETE:max_output_tokens"):
        call(context)
    assert context.budget.usage()["tokens"]["output_tokens"] == 10


def test_async_cancellation_discards_late_provider_result(context: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    entered, release, finished = Event(), Event(), Event()
    def provider(**request: object) -> Response:
        entered.set()
        assert release.wait(timeout=5)
        finished.set()
        return response()
    monkeypatch.setattr(client, "_call_api", provider)

    async def scenario() -> None:
        task = asyncio.create_task(client.aparse(step="extract", model="unit-model", instructions="extract",
            input_parts=[TextPart("<SOURCE_DATA>x</SOURCE_DATA>")], schema=Output, ctx=context, prompt_version="v1"))
        assert await asyncio.to_thread(entered.wait, 5)
        task.cancel()
        try:
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            release.set()
        assert await asyncio.to_thread(finished.wait, 5)
    asyncio.run(scenario())
    assert not list(config.settings.replay_dir.rglob("*.json"))
    assert context.trace.rows == []


def test_recording_io_error_is_typed_and_traced(context: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    config.settings.replay_dir.mkdir()
    (config.settings.replay_dir / "extract").write_text("blocked by a file", encoding="utf-8")
    monkeypatch.setattr(client, "_call_api", lambda **kwargs: response())
    with pytest.raises(client.LLMError, match="RECORDING_WRITE_FAILED"):
        call(context)
    assert context.trace.rows[-1]["error"] == "API_ERROR:RECORDING_WRITE_FAILED"
    assert context.budget.model_calls == 1 and context.budget.usage()["tokens"]["output_tokens"] == 10
