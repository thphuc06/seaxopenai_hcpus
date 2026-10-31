"""Stage-A S1 acceptance contract; expectations come from specs, never gold."""
from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import closing
from importlib import import_module
import json
from pathlib import Path
import sqlite3
import unicodedata

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from app import config
from app.models import (
    AdmitResult, Citation, EventEnvelope, FieldDecision, PassportResponse, PUBLIC_FIELDS,
)
from conftest import BUYER, OPERATOR, REVIEWER
from test_guards import FORBIDDEN

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures"
PRODUCT = "DEMO-PROD-S1"
CASE = "DEMO-CASE-S1"
STORY = (
    ("01-bootstrap-demo", "ADMITTED"),
    ("02-price-change", "NOOP"),
    ("03-duplicate-price-change", "DUPLICATE"),
    ("08-rejected-producer", "REJECTED"),
)
pytestmark = pytest.mark.phase(1)
Fire = Callable[[str], Response]


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Replace only the documented external-client seam; count even caught errors."""
    calls: list[str] = []

    def forbidden_call(**request: object) -> None:
        calls.append("model")
        raise AssertionError("Acceptance fallback tests must not call a model")

    monkeypatch.setattr("app.llm.client._call_api", forbidden_call)
    yield
    assert calls == [], "A model call was attempted in fallback acceptance tests"


def rows(query: str, params: tuple[object, ...] = ()) -> list[sqlite3.Row]:
    with closing(sqlite3.connect(
        f"file:{config.settings.db_path.as_posix()}?mode=ro", uri=True,
    )) as db:
        db.row_factory = sqlite3.Row
        return list(db.execute(query, params))


def all_counts() -> dict[str, int]:
    """Include evidence, requests, jobs (when implemented), caches and FTS tables."""
    names = rows("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    return {
        row["name"]: rows('SELECT COUNT(*) FROM "' + row["name"].replace('"', '""') + '"')[0][0]
        for row in names
    }


def admission(response: Response, expected: str) -> AdmitResult:
    assert response.is_success, (response.status_code, response.text)
    result = AdmitResult.model_validate(response.json())
    assert result.outcome == expected
    return result


def read_passport(client: TestClient, product_id: str = PRODUCT, *, reviewer: bool = False) -> PassportResponse:
    response = client.get(
        f"/api/products/{product_id}/passport", headers=REVIEWER if reviewer else BUYER,
    )
    assert response.status_code == 200, response.text
    return PassportResponse.model_validate(response.json())


def event(name: str) -> EventEnvelope:
    value = json.loads((FIXTURES / "events" / f"{name}.json").read_text(encoding="utf-8"))
    value.pop("expect")
    return EventEnvelope.model_validate(value)


def run_story(fire: Fire) -> None:
    for name, expected in STORY:
        admission(fire(name), expected)


def normalized(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def check_citation(citation: Citation) -> None:
    matches = rows(
        "SELECT p.text, p.locator, sv.version, s.kind, s.status "
        "FROM passages p JOIN source_versions sv ON sv.id=p.source_version_id "
        "JOIN sources s ON s.id=sv.source_id WHERE p.id=?", (citation.passage_id,),
    )
    assert len(matches) == 1, citation
    stored = matches[0]
    assert citation.locator == stored["locator"]
    assert citation.source_kind == stored["kind"]
    assert citation.source_version == stored["version"]
    assert stored["status"] == "ACTIVE"
    assert normalized(citation.excerpt), citation
    assert normalized(citation.excerpt) in normalized(stored["text"]), citation


@pytest.mark.needs("P1", "P2")
def test_foaming_harmless_wording(client: TestClient, fire: Fire) -> None:
    """AC-01: real R2 only; missing capture is the explicit P4 fixture exception."""
    path = FIXTURES / "events/15-bootstrap-real-foaming.json"
    if not path.exists():
        pytest.skip("AC-01: real R2 Foaming capture/event due from P4-2b at S2")
    envelope = event(path.stem)
    product_id = envelope.payload["product_id"]
    assert isinstance(product_id, str)
    products = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in (FIXTURES / "real").glob("*/product.json")
    ]
    assert any(p["product_id"] == product_id for p in products), "R2 event has no captured real product"
    admission(fire(path.stem), "ADMITTED")
    passport = read_passport(client, product_id, reviewer=True)
    fields = {field.field_key: field for field in passport.fields}
    assert set(fields) == set(PUBLIC_FIELDS)
    for key in ("volume", "skin_type", "key_ingredients"):
        assert fields[key].verdict in {"CONSISTENT", "SINGLE_SOURCE"}
    assert all(field.verdict != "CONFLICTING" for field in fields.values())


@pytest.mark.needs("P1", "P2")
def test_demo_bootstrap(client: TestClient, fire: Fire) -> None:
    """AC-05 and the S1 click-path expectations from DATASET-SPEC §4."""
    result = admission(fire("01-bootstrap-demo"), "ADMITTED")
    assert result.job_id is not None
    passport = read_passport(client, reviewer=True)
    assert passport.dataset_origin == "SYNTHETIC"
    assert passport.run_status == "COMPLETED"
    fields = {field.field_key: field for field in passport.fields}
    assert set(fields) == set(PUBLIC_FIELDS)
    for key, field in fields.items():
        assert field.verdict == ("SINGLE_SOURCE" if key == "skin_type" else "CONSISTENT")
        assert field.freshness == "CURRENT"
        assert field.citations
    for key in ("notification_number", "responsible_company"):
        assert any(c.source_kind == "NOTIFICATION_DOC" for c in fields[key].citations)


@pytest.mark.needs("P1", "P2")
@pytest.mark.parametrize("changed", [("price",), ("stock",), ("price", "stock", "promo")])
def test_price_change_noop(client: TestClient, fire: Fire, changed: tuple[str, ...]) -> None:
    """AC-07: non-material subsets must not enqueue work or touch evidence."""
    admission(fire("01-bootstrap-demo"), "ADMITTED")
    envelope = event("02-price-change")
    envelope.changed_fields = list(changed)
    before = all_counts()
    usage_before = [tuple(row) for row in rows("SELECT id, usage_json FROM runs ORDER BY id")]
    result = admission(client.post("/api/internal/events", headers=OPERATOR,
                                   json=envelope.model_dump(mode="json")), "NOOP")
    assert result.job_id is None
    assert result.stale_fields == []
    after = all_counts()
    assert after.pop("events") == before.pop("events") + 1
    assert after == before
    assert [tuple(row) for row in rows("SELECT id, usage_json FROM runs ORDER BY id")] == usage_before


@pytest.mark.needs("P1", "P2")
@pytest.mark.parametrize("first,repeat", [
    ("02-price-change", "03-duplicate-price-change"),
    ("01-bootstrap-demo", "01-bootstrap-demo"),
])
def test_duplicate_event_idempotent(fire: Fire, first: str, repeat: str) -> None:
    """AC-08: both NOOP and material admitted keys have zero repeat side effects."""
    admission(fire("01-bootstrap-demo"), "ADMITTED")
    if first != "01-bootstrap-demo":
        admission(fire(first), "NOOP")
    before = all_counts()
    admission(fire(repeat), "DUPLICATE")
    assert all_counts() == before


@pytest.mark.needs("P1", "P2")
def test_wrong_market_excluded(client: TestClient, fire: Fire) -> None:
    """AC-10: exclusion must have an audit reason, not merely a benign verdict."""
    admission(fire("01-bootstrap-demo"), "ADMITTED")
    passport = read_passport(client, reviewer=True)
    assert len(passport.fields) == len(PUBLIC_FIELDS)
    wrong = rows(
        "SELECT p.id FROM passages p JOIN source_versions sv ON sv.id=p.source_version_id "
        "WHERE sv.source_id=?", ("DEMO-SRC-S1-BRAND-PH",),
    )
    wrong_ids = {row["id"] for row in wrong}
    assert wrong_ids
    for field in passport.fields:
        assert field.verdict != "CONFLICTING"
        assert not wrong_ids.intersection(c.passage_id for c in field.citations)
    scopes = rows(
        "SELECT ps.scope_match, ps.reason FROM passage_scopes ps "
        "JOIN source_versions sv ON sv.id=ps.source_version_id WHERE sv.source_id=?",
        ("DEMO-SRC-S1-BRAND-PH",),
    )
    # Source-level scope may be recorded in the trace rather than passage_scopes.
    trace = rows("SELECT input_refs, output_refs, detail FROM trace_steps WHERE step='scope_check'")
    trace_text = " ".join(str(value) for row in trace for value in row if value)
    passage_reason = bool(scopes) and all(
        row["scope_match"] == "MISMATCH" and row["reason"] for row in scopes
    )
    source_versions = rows("SELECT id FROM source_versions WHERE source_id=?", ("DEMO-SRC-S1-BRAND-PH",))
    trace_reason = (
        any(ref in trace_text for ref in ["DEMO-SRC-S1-BRAND-PH", *[r["id"] for r in source_versions]])
        and "MISMATCH" in trace_text and "reason" in trace_text
    )
    assert passage_reason or trace_reason, "Missing attributable scope exclusion and reason"


@pytest.mark.needs("P1", "P2")
def test_buyer_read_only(client: TestClient, fire: Fire, counts: Callable[[], dict[str, int]]) -> None:
    """AC-13: five reads create no persistent work, including searches and requests."""
    admission(fire("01-bootstrap-demo"), "ADMITTED")
    before, comprehensive = counts(), all_counts()
    usage = [tuple(row) for row in rows("SELECT id, usage_json FROM runs ORDER BY id")]
    for _ in range(5):
        assert len(read_passport(client).fields) == len(PUBLIC_FIELDS)
    assert counts() == before
    assert all_counts() == comprehensive
    assert [tuple(row) for row in rows("SELECT id, usage_json FROM runs ORDER BY id")] == usage


@pytest.mark.needs("P1")
def test_buyer_cannot_post_events(client: TestClient) -> None:
    """AC-14: authorization precedes event admission."""
    before = all_counts()
    response = client.post("/api/internal/events", headers=BUYER,
                           json=event("01-bootstrap-demo").model_dump(mode="json"))
    assert response.status_code == 403
    assert all_counts() == before


@pytest.mark.needs("P1")
def test_rejected_producer(client: TestClient, fire: Fire) -> None:
    before = all_counts()
    result = admission(fire("08-rejected-producer"), "REJECTED")
    assert result.job_id is None
    assert result.stale_fields == []
    assert result.reason
    after = all_counts()
    assert after.pop("events") == before.pop("events") + 1
    assert after == before


@pytest.mark.needs("P1", "P2")
def test_old_run_no_overwrite(client: TestClient, fire: Fire) -> None:
    """AC-16: user-approved direct public gate test; writes only arrange stale run."""
    admission(fire("01-bootstrap-demo"), "ADMITTED")
    passport = read_passport(client, reviewer=True)
    field = next(field for field in passport.fields if field.field_key == "volume")
    assert field.citations
    case = dict(rows("SELECT * FROM cases WHERE id=?", (CASE,))[0])
    run = dict(rows("SELECT * FROM runs WHERE case_id=? ORDER BY case_revision DESC LIMIT 1", (CASE,))[0])
    run["id"] = "acceptance-stale-run"
    run["case_revision"] = case["revision"] - 1
    run["status"] = "RUNNING"
    # Setup only: a delayed older run exists while a newer revision is published.
    with closing(sqlite3.connect(config.settings.db_path)) as db:
        with db:
            db.execute(
                "INSERT INTO runs(id, case_id, case_revision, status) VALUES (?, ?, ?, ?)",
                (run["id"], CASE, run["case_revision"], run["status"]),
            )
    before = [tuple(row) for row in rows("SELECT * FROM field_results ORDER BY id")]
    decision = FieldDecision(
        field_key="volume", verdict="SINGLE_SOURCE", conflict_locus=None,
        scope_match="MATCH", review_state="AUTO_DRAFT", evidence_level="PRODUCT_VERSION",
        seller_attributable=False, citations=field.citations, depends_on=[],
        public_text="50 ml — stated by the packaging only.", notes=[], explain=[],
        gap=None, needs_scope_resolution=False,
    )
    publish = import_module("app.pipeline.publish")
    publish.gate(decision, run, case)
    assert [tuple(row) for row in rows("SELECT * FROM field_results ORDER BY id")] == before
    trace = rows("SELECT step, detail, error FROM trace_steps WHERE run_id=?", (run["id"],))
    assert any(
        row["step"] == "publish:blocked" and "SUPERSEDED_RUN" in " ".join(str(v) for v in row if v)
        for row in trace
    ), "Stale run must be rejected with a SUPERSEDED_RUN audit trace"


@pytest.mark.needs("P1", "P2")
def test_no_authenticity_claims(client: TestClient, fire: Fire) -> None:
    """AC-19: every stored/public text after the complete S1 story."""
    run_story(fire)
    stored = rows("SELECT public_text FROM field_results")
    assert stored
    texts = [row["public_text"] for row in stored]
    for reviewer in (False, True):
        passport = read_passport(client, reviewer=reviewer)
        assert len(passport.fields) == len(PUBLIC_FIELDS)
        texts.extend(field.public_text for field in passport.fields)
        texts.append(passport.disclaimer)
    assert all(isinstance(text, str) and text.strip() for text in texts)
    assert not [text for text in texts if FORBIDDEN.search(text)]


@pytest.mark.needs("P1", "P2")
def test_citations_valid(client: TestClient, fire: Fire) -> None:
    """AC-20: persisted findings include private evidence; buyer filtering is separate."""
    run_story(fire)
    results = rows("SELECT verdict, citations_json FROM field_results")
    assert len(results) >= len(PUBLIC_FIELDS)
    for result in results:
        citations = [Citation.model_validate(c) for c in json.loads(result["citations_json"])]
        if result["verdict"] != "INSUFFICIENT":
            assert citations, result["verdict"]
        for citation in citations:
            check_citation(citation)
    for field in read_passport(client, reviewer=True).fields:
        if field.verdict != "INSUFFICIENT":
            assert field.citations
        for citation in field.citations:
            check_citation(citation)
