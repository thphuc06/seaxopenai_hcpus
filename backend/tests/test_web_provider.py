"""Transport bounds and immutable web replay, with no external requests."""
import json

from openai.types.responses import Response
import pytest

from app import config
from app.budget import Budget, BudgetExceeded
from app.connectors import websearch
from app.context import RunContext
from app.llm import client
from test_web import context  # Shared real database setup; no production function replacement.


def session(ctx: RunContext) -> websearch.WebSession:
    return websearch.WebSession(ctx, ["aurora.example"], "Aurora", "VN")


def response(*, status: str = "completed", refusal: bool = False) -> Response:
    content = [{"type": "refusal", "refusal": "declined"}] if refusal else [{"type": "output_text",
        "text": "Generated answer is not evidence", "annotations": [{"type": "url_citation", "start_index": 0,
            "end_index": 4, "url": "https://aurora.example/gel", "title": "Aurora Meadow Gel"}]}]
    return Response.model_validate({"id": "resp", "object": "response", "created_at": 0,
        "model": "unit", "status": status, "parallel_tool_calls": False, "tool_choice": "auto", "tools": [],
        "usage": {"input_tokens": 12, "output_tokens": 9, "total_tokens": 21,
                  "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0}, "output_tokens_details": {"reasoning_tokens": 2}},
        "output": [{"type": "web_search_call", "id": "search", "status": "completed",
                    "action": {"type": "search", "query": "Aurora", "sources": [{"type": "url", "url": "https://aurora.example/gel"}]}},
                   {"type": "message", "id": "message", "role": "assistant", "status": "completed", "content": content}]})


def test_hosted_request_and_record_replay_immutable(context: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []
    def call(**request: object) -> Response:
        calls.append(request)
        return response()
    monkeypatch.setattr(client, "_call_api", call)
    context.mode = "record"
    first = session(context).search("Aurora Meadow Gel")
    assert first[0].title == "Aurora Meadow Gel" and first[0].snippet == ""
    request = calls[0]
    assert request["max_tool_calls"] == 1 and request["include"] == ["web_search_call.action.sources"]
    assert request["tools"][0]["filters"] == {"allowed_domains": ["aurora.example"]}
    assert context.budget.model_calls == context.budget.tool_calls == 1
    assert context.budget.usage()["tokens"] == {"input_tokens": 12, "output_tokens": 9, "reasoning_tokens": 2}
    path = next((config.settings.replay_dir / "web").glob("*.json"))
    original = path.read_bytes()
    assert json.loads(original)["usage"]["input_tokens"] == 12
    assert session(context).search("Aurora Meadow Gel") == first
    context.mode = "replay"
    assert session(context).search("Aurora Meadow Gel") == first
    assert len(calls) == 1 and context.budget.model_calls == context.budget.tool_calls == 3
    assert path.read_bytes() == original
    with pytest.raises(client.LLMError, match="REPLAY_MISS"):
        session(context).search("Aurora changed query")
    context.mode = "live"
    session(context).search("Aurora Meadow Gel")
    assert len(calls) == 2 and path.read_bytes() == original


@pytest.mark.parametrize("status,refusal,reason", [("incomplete", False, "INCOMPLETE"), ("completed", True, "REFUSAL")])
def test_provider_status_errors_metered_no_recording(context: RunContext, monkeypatch: pytest.MonkeyPatch,
                                                  status: str, refusal: bool, reason: str) -> None:
    context.mode = "record"
    monkeypatch.setattr(client, "_call_api", lambda **kwargs: response(status=status, refusal=refusal))
    with pytest.raises(client.LLMError, match=reason):
        session(context).search("Aurora query")
    assert context.budget.model_calls == 1 and context.budget.usage()["tokens"]["input_tokens"] == 12
    assert not list(config.settings.replay_dir.rglob("*.json"))


def test_fetch_record_and_replay(context: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    context.mode = "record"
    requested: list[str] = []
    def http(url: str, *, timeout: float) -> websearch.Page:
        requested.append(url)
        assert timeout > 0
        return websearch.Page(url=url, status=200, text="Aurora Meadow Gel. Capacity 38 ml.", fetched_at="2026-10-31T07:00:00Z")
    monkeypatch.setattr(websearch, "_fetch_http", http)
    first = session(context)
    first.returned_urls.add("https://aurora.example/gel")
    page = first.fetch("https://aurora.example/gel")
    context.mode = "replay"
    second = session(context)
    second.returned_urls.add(page.url)
    assert second.fetch(page.url) == page and requested == [page.url]
    assert context.budget.model_calls == 0 and context.budget.tool_calls == 2


@pytest.mark.parametrize("url", ["file:///secret", "http://127.0.0.1/x", "https://aurora.example@evil.example/x",
    "https://aurora.example.evil.example/x", "https://aurora.example:8080/x", "https://aurora.example/missing"])
def test_invalid_or_unreturned_url_never_fetches(context: RunContext, url: str) -> None:
    with pytest.raises(websearch.WebError):
        session(context).fetch(url)
    assert context.budget.tool_calls == 0


@pytest.mark.parametrize("query", ["Other brand", "", "Aurora " + "x" * 501])
def test_query_gate_precedes_provider(context: RunContext, query: str) -> None:
    with pytest.raises(websearch.WebError, match="INVALID_QUERY"):
        session(context).search(query)
    assert context.budget.tool_calls == context.budget.model_calls == 0


def test_fallback_freeze_no_network_and_repeat_gate(context: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPLAY_FREEZE", "1")
    config.reload_settings()
    transport = session(context)
    assert transport.search("Aurora query") == []
    with pytest.raises(websearch.WebError, match="REPEATED_QUERY"):
        transport.search("  AURORA   query ")
    assert context.budget.tool_calls == 1 and context.budget.model_calls == 0
    context.mode = "live"
    with pytest.raises(client.LLMError, match="REPLAY_MISS"):
        session(context).search("Aurora different")


def test_deadline_and_agent_caps_before_network(context: RunContext) -> None:
    context.budget = Budget(deadline_s=0)
    with pytest.raises(BudgetExceeded, match="RUN_DEADLINE"):
        session(context).search("Aurora query")
    assert context.budget.tool_calls == 0
    context.budget = Budget()
    context.budget.agent().max_tool_calls = 0
    with pytest.raises(BudgetExceeded, match="AGENT_TOOL_CALLS"):
        session(context).search("Aurora query")
    assert context.budget.tool_calls == 0


@pytest.mark.parametrize("failure", ["target", "size", "status"])
def test_invalid_fetch_result_rejected(context: RunContext, monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    url = "https://aurora.example/gel"
    monkeypatch.setattr(websearch, "fetch", lambda target: websearch.Page(
        url="https://elsewhere.example/gel" if failure == "target" else target,
        status=302 if failure == "status" else 200, text="x" * (websearch.MAX_BYTES + 1) if failure == "size" else "body",
        fetched_at="2026-10-31T07:00:00Z"))
    transport = session(context)
    transport.returned_urls.add(url)
    with pytest.raises(websearch.WebError):
        transport.fetch(url)
    assert context.budget.tool_calls == 1


@pytest.mark.parametrize("damage", ["key", "schema", "output"])
def test_corrupt_recording_fails_closed(context: RunContext, monkeypatch: pytest.MonkeyPatch, damage: str) -> None:
    context.mode = "record"
    monkeypatch.setattr(client, "_call_api", lambda **kwargs: response())
    session(context).search("Aurora query")
    path = next((config.settings.replay_dir / "web").glob("*.json"))
    data = json.loads(path.read_text(encoding="utf-8"))
    data[damage] = {} if damage != "key" else "changed"
    path.write_text(json.dumps(data), encoding="utf-8")
    context.mode = "replay"
    with pytest.raises(client.LLMError, match="INVALID_RECORDING"):
        session(context).search("Aurora query")


def test_private_dns_preflight_rejects_before_http(context: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(websearch.socket, "getaddrinfo", lambda *args, **kwargs: [(2, 1, 6, "", ("127.0.0.1", 443))])
    monkeypatch.setattr(websearch.httpx, "Client", lambda **kwargs: pytest.fail("private destination reached HTTP"))
    # Exercise the actual HTTP boundary, not the fixture's replacement.
    with pytest.raises(websearch.WebError, match="NONPUBLIC_ADDRESS"):
        _http_boundary("https://aurora.example/gel", timeout=1)


_http_boundary = websearch._fetch_http
