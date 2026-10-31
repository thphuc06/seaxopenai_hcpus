"""Server-owned boundaries for post-ingest indexing and optional agent search."""
from dataclasses import replace

from app import db
from app.context import RunContext
from app.retrieval import search as retrieval


def _versions(ctx: RunContext) -> list[str]:
    with db.transaction() as connection:
        case = connection.execute("SELECT tenant_id,revision,product_id FROM cases WHERE id=?", (ctx.case_id,)).fetchone()
        if not case or (case["tenant_id"], case["revision"], case["product_id"]) != (
                ctx.tenant_id, ctx.case_revision, ctx.product.get("id")):
            raise PermissionError("ACCESS_DENIED")
        return [row[0] for row in connection.execute(
            "SELECT v.id FROM source_versions v JOIN sources s ON s.id=v.source_id "
            "WHERE s.case_id=? AND s.status='ACTIVE' AND v.is_current=1", (ctx.case_id,))]


def reindex_sources(ctx: RunContext, source_version_ids: list[str]) -> None:
    """Call after ingest commits and a run exists; debit that run, never a new Budget."""
    allowed = set(_versions(ctx))
    if not set(source_version_ids) <= allowed:
        raise PermissionError("ACCESS_DENIED")
    ctx.budget.check_active()
    with retrieval.run_context(ctx):
        for sv_id in dict.fromkeys(source_version_ids):
            retrieval.index_source_version(sv_id)


def search_case_corpus(ctx: RunContext, query: str, *, k: int = 8) -> retrieval.SearchResult:
    """Optional agent-only search; the single-call scope path never invokes it."""
    versions = _versions(ctx)
    child = ctx.budget.agent().gateway()
    child.take_tool("search_case_corpus")
    with ctx.trace.timed("agent:tool:search_case_corpus"):
        with retrieval.run_context(replace(ctx, budget=child)):
            return retrieval.search(ctx.case_id, query, k=k, allowed_sv_ids=versions)
