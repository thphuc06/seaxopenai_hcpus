"""Evidence writes recheck run identity after the web preflight transaction."""
from dataclasses import replace

import pytest

from app import db, store
from app.budget import Budget
from app.context import RunContext
from app.pipeline.web_sources import _snapshot
from app.trace import TraceWriter
from p1_helpers import CoreDB, core_db


class RevisionChangeBudget(Budget):
    """Schedule a committed event between preflight and the evidence write."""

    checks: int = 0

    def check_active(self) -> None:
        super().check_active()
        self.checks += 1
        if self.checks == 2:
            with db.transaction() as connection:
                connection.execute("UPDATE cases SET revision=revision+1")


def context(core: CoreDB) -> RunContext:
    run = core.run()
    return RunContext(str(run["id"]), core.case_id, "unit-tenant", 0,
                      {"id": core.product_id}, "fallback", Budget(), TraceWriter(str(run["id"])))


def snapshot(ctx: RunContext, text: str) -> tuple[str, bool]:
    return _snapshot(ctx, ctx.product, "https://example.org/item", "2026-10-31T09:00:00Z",
                     text, True, "WEB_PAGE", "example.org")


@pytest.mark.parametrize("existing", [False, True])
def test_revision_change_after_preflight_cannot_install_source(core_db: CoreDB, existing: bool) -> None:
    ctx = context(core_db)
    if existing:
        snapshot(ctx, "Volume: 83 ml. Existing stored reference passage.")
    before = {table: core_db.rows(f"SELECT * FROM {table}")
              for table in ("sources", "source_versions", "passages", "passages_fts")}
    stale = replace(ctx, budget=RevisionChangeBudget())
    with pytest.raises(PermissionError, match="ACCESS_DENIED_OR_SUPERSEDED_RUN"):
        snapshot(stale, "Volume: 97 ml. New reference from the now outdated run.")
    assert stale.budget.checks == 2
    assert core_db.rows("SELECT revision FROM cases") == [{"revision": 1}]
    assert {table: core_db.rows(f"SELECT * FROM {table}") for table in before} == before


@pytest.mark.parametrize("mismatch", ["tenant", "run", "product", "revision"])
def test_source_write_context_rejects_identity_mismatch(core_db: CoreDB, mismatch: str) -> None:
    ctx = context(core_db)
    expected = store.SourceWriteContext(ctx.run_id, ctx.tenant_id, ctx.case_revision)
    if mismatch == "tenant":
        expected = replace(expected, tenant_id="another-tenant")
    elif mismatch == "run":
        expected = replace(expected, run_id="missing-run")
    elif mismatch == "revision":
        expected = replace(expected, case_revision=1)
    evidence = {"source_id": "reference", "product_id": "another-product" if mismatch == "product" else core_db.product_id,
                "kind": "WEB_PAGE", "version": 1,
                "passages": [{"locator": "paragraph:1", "text": "Volume: 83 ml."}]}
    before = core_db.dump()
    with pytest.raises(PermissionError, match="ACCESS_DENIED_OR_SUPERSEDED_RUN"):
        store.add_source_version(evidence, case_id=core_db.case_id, origin="SYNTHETIC", expected_context=expected)
    assert core_db.dump() == before


def test_current_run_can_ingest_and_retry_idempotently(core_db: CoreDB) -> None:
    ctx = context(core_db)
    first, created = snapshot(ctx, "Volume: 83 ml. Current reference passage for this product.")
    assert created
    assert snapshot(ctx, "Volume: 83 ml. Current reference passage for this product.") == (first, False)
    assert core_db.rows("SELECT COUNT(*) AS n FROM source_versions") == [{"n": 1}]
