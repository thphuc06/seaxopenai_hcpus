"""Integration regressions with unrelated inputs and real policy/storage seams."""
from dataclasses import replace

import pytest

from app import db, store, worker
from app.context import RunContext
from app.events.admit import admit
from app.models import Role, ScopeMatch, SourceKind
from app.pipeline import claims_audit, normalize, publish
from p1_helpers import CoreDB, core_db
from test_claims import observation
from test_extract import context, source


@pytest.mark.parametrize("name", ["Hydrolyzed Hyaluronic Acid", "HYDROLYZED SODIUM HYALURONATE."])
def test_sourced_hyaluronate_family_in_inci(name: str) -> None:
    normalized = normalize.normalize("inci_list", f"Water, {name}, Glycerin")
    assert normalized is not None
    assert normalized["value"] == ["WATER", "HYALURONIC_ACID", "GLYCERIN"]
    assert normalize.normalize("inci_list", "Hydrolyzed Unlisted Acid")["value"] == ["HYDROLYZED UNLISTED ACID"]


@pytest.mark.parametrize("text", ["Chai 83 ml; tặng mẫu 29 ml", "Bottle 83 ml; free gift 11 ml"])
def test_filtered_gift_keeps_source_attributed_trace(core_db: CoreDB, text: str) -> None:
    obs = core_db.source("trace-listing", kind="LISTING", text=text)
    admission = admit(core_db.event(), role=Role.OPERATOR, actor_id="operator")
    worker.execute_job(admission.job_id)
    steps = core_db.rows("SELECT input_refs,detail FROM trace_steps WHERE step='scope_check'")
    assert any("GIFT_CONTEXT" in str(row["detail"]) and obs.passage_id in str(row["input_refs"]) for row in steps)
    assert core_db.rows("SELECT verdict FROM field_results WHERE field_key='volume'") == [{"verdict": "SINGLE_SOURCE"}]


@pytest.mark.parametrize("placement", ["MISMATCH", "UNKNOWN", "AGENT"])
@pytest.mark.parametrize("reverse", [False, True])
def test_claim_audit_preserves_each_passage_scope(context: RunContext, placement: str, reverse: bool) -> None:
    context.product.update(case_id=context.case_id, tenant_id=context.tenant_id)
    sv = source(["Target bottle 47 ml.", "Alcohol-free."])
    passages = store.passages(sv)
    with db.transaction() as connection:
        connection.execute("UPDATE runs SET case_revision=? WHERE id=?", (context.case_revision, context.run_id))
        connection.execute(
            "INSERT INTO passage_scopes(source_version_id,passage_id,scope_match,reason,decided_by,run_id,created_at) VALUES(?,?,?,?,?,?,?)",
            (sv, passages[1]["id"], placement, "Variant placement", "CODE", context.run_id, db.now_iso()),
        )
    matched = observation(sv)
    placed = replace(matched, passage_id=passages[1]["id"], locator=passages[1]["locator"], scope_match=ScopeMatch(placement))
    reference = source(["Water, Alcohol Denat., Glycerin"], source_id="reference")
    with db.transaction() as connection:
        connection.execute("UPDATE sources SET kind='BRAND_PAGE' WHERE id='reference'")
    inci = observation(reference, kind=SourceKind.BRAND_PAGE, field="inci_list", quote="Water, Alcohol Denat., Glycerin",
                       normalized=normalize.normalize("inci_list", "Water, Alcohol Denat., Glycerin"))
    listing = [matched, placed][::-1] if reverse else [matched, placed]
    findings = claims_audit.audit(context, listing, [*listing, inci])
    if placement == "MISMATCH":
        assert findings == []
    else:
        assert findings and all(f.scope_match == placement and f.verdict != "CONFLICTING" for f in findings)
        for finding in findings:
            assert publish.gate(finding, {"id": context.run_id, "case_revision": 1}, {"id": context.case_id})

