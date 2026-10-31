"""P4 phase3 path catches missing evidence, mode substitution and buyer leaks."""
from collections.abc import Callable
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys

import httpx
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.models import PUBLIC_FIELDS
from scripts.sync_check import CaseState, PhaseThreeProbe, ScopeProbe, run_phase_three, phase_three_probe
from app import config
from test_sync_phase_two import field


@pytest.mark.parametrize("mode,fault", [
    ("fallback", None), ("replay", None), ("fallback", "invented-effect"), ("fallback", "resolved-line"),
    ("replay", "no-anchor"), ("replay", "no-effect"), ("replay", "no-change"),
    ("replay", "miss"), ("replay", "no-registry"), ("fallback", "leak"),
    ("fallback", "side-effect"), ("fallback", "missing-route"), ("replay", "wrong-mode"),
])
def test_phase_three_checks_observed_contract(mode: str, fault: str | None) -> None:
    catalogue = False
    reads = 0

    def state(case: str) -> CaseState:
        fields = {key: field(key) for key in PUBLIC_FIELDS}
        if case == "main":
            fields["skin_type"] = field("skin_type", "CONSISTENT" if catalogue and mode == "replay" and fault != "no-change" else "SINGLE_SOURCE")
        return CaseState(1, fields, True, True, True)

    def probe(case: str) -> PhaseThreeProbe:
        scopes = [ScopeProbe(scope_match=match, decided_by="CODE", anchor_passage_id=None) for match in ("MATCH", "MISMATCH")]
        if mode == "fallback":
            if fault != "resolved-line":
                scopes.append(ScopeProbe(scope_match="UNKNOWN", decided_by="CODE", anchor_passage_id=None))
        else:
            scopes.append(ScopeProbe(scope_match="MATCH", decided_by="AGENT_VERIFIED", anchor_passage_id=None if fault == "no-anchor" else "anchor"))
        effects = [{"before": {"skin_type": "SINGLE_SOURCE"}, "after": {"skin_type": "CONSISTENT"}}] if mode == "replay" or fault == "invented-effect" else []
        return PhaseThreeProbe(mode="FALLBACK" if fault == "wrong-mode" else mode.upper(),
            status="PARTIAL" if fault == "miss" else "COMPLETED", stop_reason="REPLAY_MISS" if fault == "miss" else None,
            scopes=scopes, effects=[] if fault == "no-effect" else effects,
            registry_closed=fault != "no-registry", private_fragments=["private-document", "model-secret", "R3"])

    def transport(request: httpx.Request) -> httpx.Response:
        nonlocal catalogue, reads
        if request.method == "POST":
            if request.url.path.endswith("09-catalogue-published"):
                catalogue = True
            return httpx.Response(200, json={"event_id": "evt", "outcome": "ADMITTED", "reason": "accepted",
                                            "job_id": "job", "stale_fields": []})
        reads += 1
        if fault == "missing-route":
            return httpx.Response(404, json={"detail": "absent"})
        buyer = request.headers["X-Demo-Role"] == "BUYER"
        return httpx.Response(200, json={"summary": "private-document" if buyer and fault == "leak" else "Source comparison"})

    with httpx.Client(transport=httpx.MockTransport(transport), base_url="http://test") as client:
        checks = run_phase_three(client, state, lambda: {"rows": reads if fault == "side-effect" else 0}, probe,
                                 "other-product", "main", "sun-product", "sun", expected_mode=mode)
    assert any(check.status == "FAIL" for check in checks) is (fault is not None)
    if fault is None:
        assert len(checks) == 3


def test_probe_reads_real_run_and_distinguishes_mode_from_model_id(client: TestClient, fire: Callable[[str], httpx.Response]) -> None:
    response = fire("01-bootstrap-demo")
    assert response.status_code == 200
    with closing(sqlite3.connect(config.settings.db_path)) as connection:
        case_id = connection.execute("SELECT case_id FROM runs LIMIT 1").fetchone()[0]
    before = config.settings.db_path.read_bytes()
    probe = phase_three_probe(config.settings.db_path, case_id)
    assert probe.mode == "FALLBACK" and probe.status == "COMPLETED"
    assert "FALLBACK" not in probe.private_fragments
    assert probe.private_fragments  # Private source text/rules still must be filtered.
    assert config.settings.db_path.read_bytes() == before


@pytest.mark.parametrize("fault", [None, "proposal", "model-actor", "foreign-version", "old-run", "unverified", "missing", "ambiguous"])
def test_probe_requires_current_code_validation_for_stored_anchor(tmp_path: Path, fault: str | None) -> None:
    """Independent minimal SQLite fixture mirrors the existing columns, not an invented anchor column."""
    path = tmp_path / "probe.db"
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript("""
            CREATE TABLE runs(id,case_id,case_revision,created_at,llm_mode,status,stop_reason,model);
            CREATE TABLE passage_scopes(source_version_id,passage_id,scope_match,decided_by,run_id);
            CREATE TABLE trace_steps(run_id,step,actor,error,detail);
            CREATE TABLE passages(id,source_version_id,text);
            CREATE TABLE source_versions(id,source_id);
            CREATE TABLE sources(id,case_id,visibility);
            CREATE TABLE field_results(case_id,superseded_by,explain_json);
            INSERT INTO runs VALUES('current','arbitrary-case',2,'2026-10-31T06:00:00Z','REPLAY','COMPLETED',NULL,'model-id');
            INSERT INTO runs VALUES('old','arbitrary-case',1,'2026-10-31T05:00:00Z','REPLAY','COMPLETED',NULL,'model-id');
            INSERT INTO passages VALUES('target','version-a','size-less line');
            INSERT INTO passages VALUES('anchor','version-a','137 ml heading');
            INSERT INTO passages VALUES('alternative','version-a','212 ml heading');
            INSERT INTO passage_scopes VALUES('version-a','target','MATCH','AGENT_VERIFIED','current');
        """)
        detail = dict(passage_id="target", sv_id="version-a", scope_match="MATCH", decided_by="AGENT_VERIFIED",
                      anchor_passage_id="anchor", reason="code validation")
        if fault == "foreign-version":
            connection.execute("UPDATE passages SET source_version_id='version-b' WHERE id='anchor'")
        if fault == "unverified":
            detail["decided_by"] = "AGENT"
        if fault != "missing":
            connection.execute("INSERT INTO trace_steps VALUES(?,?,?,?,?)", (
                "old" if fault == "old-run" else "current",
                "agent:proposal" if fault == "proposal" else "scope:validate",
                "llm" if fault == "model-actor" else "code", None, json.dumps(detail)))
        if fault == "ambiguous":
            connection.execute("INSERT INTO trace_steps VALUES('current','scope:validate','code',NULL,?)",
                               (json.dumps({**detail, "anchor_passage_id": "alternative"}),))
        connection.commit()
    probe = phase_three_probe(path, "arbitrary-case")
    assert len(probe.scopes) == 1
    assert probe.scopes[0].anchor_passage_id == ("anchor" if fault is None else None)
