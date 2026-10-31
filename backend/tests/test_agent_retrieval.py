"""Main-lane context wiring over the handed-off retrieval implementation."""
from dataclasses import replace

import pytest

from app import config, db
from app.agent.retrieval import reindex_sources, search_case_corpus
from app.budget import BudgetExceeded
from app.context import RunContext
from app.retrieval.search import search
from test_retrieval_embeddings import ctx, provider, source


@pytest.fixture(autouse=True)
def restore_settings(monkeypatch: pytest.MonkeyPatch):
    yield
    monkeypatch.undo()
    config.reload_settings()


def test_reindex_and_agent_query_share_run_and_child(ctx: RunContext, provider: list[str]) -> None:
    sv = source(["Glycerin content", "Other passage"])
    assert provider == []
    ctx.mode = "record"
    reindex_sources(ctx, [sv])
    assert len(provider) == ctx.budget.model_calls == 2
    result = search_case_corpus(ctx, "Glycerin")
    assert result.hits
    assert len(provider) == ctx.budget.model_calls == 3
    assert ctx.budget.agent().model_calls == 1
    assert ctx.budget.agent().tool_calls == ctx.budget.tool_calls == 1
    with db.transaction() as connection:
        before = connection.execute("SELECT COUNT(*) FROM trace_steps").fetchone()[0]
    assert search(ctx.case_id, "Glycerin").stages["metadata"][0]["effective_mode"] == "BM25 only"
    assert len(provider) == 3
    with db.transaction() as connection:
        assert connection.execute("SELECT COUNT(*) FROM trace_steps").fetchone()[0] == before


def test_context_acl_precedes_budget_or_embedding(ctx: RunContext, provider: list[str]) -> None:
    sv = source(["Private passage"], case="b")
    with pytest.raises(PermissionError, match="ACCESS_DENIED"):
        reindex_sources(ctx, [sv])
    with pytest.raises(PermissionError, match="ACCESS_DENIED"):
        search_case_corpus(replace(ctx, tenant_id="other"), "Private")
    assert not provider and ctx.budget.model_calls == ctx.budget.tool_calls == 0


def test_search_tool_limit_is_shared(ctx: RunContext, provider: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    source(["Glycerin content"])
    monkeypatch.setenv("AGENT_MAX_TOOL_CALLS", "0")
    config.reload_settings()
    with pytest.raises(BudgetExceeded, match="AGENT_TOOL_CALLS"):
        search_case_corpus(ctx, "Glycerin")
    assert not provider and ctx.budget.model_calls == ctx.budget.tool_calls == 0
