"""Stage-A S1 acceptance contract; expectations come from specs, never gold."""
from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import closing
from dataclasses import dataclass, field as data_field
from importlib import import_module
import json
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import unicodedata

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from openai import APIConnectionError
from openai.types.responses import Response as OpenAIResponse
from pydantic import BaseModel

from app import config
from app.models import (
    AdmitResult, Citation, ClaimExtraction, ExtractedClaim, EventEnvelope, FieldDecision, PassportResponse, PUBLIC_FIELDS,
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
                "INSERT INTO runs(id, case_id, case_revision, status, started_at, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (run["id"], CASE, run["case_revision"], run["status"], run["started_at"], run["created_at"]),
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


def require_events(*names: str) -> None:
    missing = [name for name in names if not (FIXTURES / "events" / f"{name}.json").exists()]
    if missing:
        pytest.skip("P4 fixture not yet supplied: " + ", ".join(missing))


def latest_result(field: str, case_id: str = CASE) -> sqlite3.Row:
    result = rows("SELECT * FROM field_results WHERE case_id=? AND field_key=? "
                  "ORDER BY result_version DESC LIMIT 1", (case_id, field))
    assert result, (case_id, field)
    return result[0]


def latest_run(case_id: str = CASE) -> sqlite3.Row:
    result = rows("SELECT * FROM runs WHERE case_id=? ORDER BY created_at DESC, rowid DESC LIMIT 1", (case_id,))
    assert result
    return result[0]


def bootstrap_named(fire: Fire, name: str) -> tuple[str, str]:
    require_events(name)
    payload = event(name).payload
    product_id, case_id = payload["product_id"], payload["case_id"]
    assert isinstance(product_id, str) and isinstance(case_id, str)
    admission(fire(name), "ADMITTED")
    return product_id, case_id


def trace_details(run_id: str, prefix: str = "") -> list[dict[str, object]]:
    return [json.loads(row["detail"]) for row in rows(
        "SELECT detail FROM trace_steps WHERE run_id=? AND step LIKE ? ORDER BY seq",
        (run_id, prefix + "%"),
    ) if row["detail"]]


@pytest.mark.phase(2)
@pytest.mark.needs("P1", "P2")
@pytest.mark.parametrize("name", ["11-bootstrap-hydra", "14-bootstrap-real-hydrating"])
def test_hydrating_self_conflict(client: TestClient, fire: Fire, name: str) -> None:
    """AC-02: exercise every supplied synthetic/real counterpart independently."""
    product_id, case_id = bootstrap_named(fire, name)
    field = next(f for f in read_passport(client, product_id, reviewer=True).fields if f.field_key == "skin_type")
    assert (field.verdict, field.conflict_locus, field.review_state) == (
        "CONFLICTING", "WITHIN_SOURCE", "NEEDS_REVIEW",
    )
    assert latest_result("skin_type", case_id)["seller_attributable"] == 0
    assert len(field.citations) >= 2


@pytest.mark.phase(2)
@pytest.mark.needs("P1", "P2")
@pytest.mark.parametrize("name", ["11-bootstrap-hydra", "14-bootstrap-real-hydrating"])
def test_hydrating_ingredient_absent_from_inci(client: TestClient, fire: Fire, name: str) -> None:
    """AC-03: both contradictory passages belong to the same source version."""
    product_id, case_id = bootstrap_named(fire, name)
    field = next(f for f in read_passport(client, product_id, reviewer=True).fields if f.field_key == "key_ingredients")
    assert (field.verdict, field.conflict_locus, field.review_state) == (
        "CONFLICTING", "WITHIN_SOURCE", "NEEDS_REVIEW",
    )
    assert latest_result("key_ingredients", case_id)["seller_attributable"] == 0
    by_version: dict[str, set[str]] = {}
    for citation in field.citations:
        check_citation(citation)
        version = rows("SELECT source_version_id FROM passages WHERE id=?", (citation.passage_id,))[0][0]
        by_version.setdefault(version, set()).add(citation.passage_id)
    assert any(len(passages) >= 2 for passages in by_version.values())


@pytest.mark.phase(2)
@pytest.mark.needs("P1", "P2")
@pytest.mark.parametrize("name,key", [("01-bootstrap-demo", "skin_type"),
                                       ("16-bootstrap-real-blemish", "key_ingredients")])
def test_blemish_single_source(client: TestClient, fire: Fire, name: str, key: str) -> None:
    """AC-04: S1 always exercises the single-family case, real R3 when captured."""
    product_id, _ = bootstrap_named(fire, name)
    field = next(f for f in read_passport(client, product_id, reviewer=True).fields if f.field_key == key)
    assert field.verdict == "SINGLE_SOURCE"
    assert field.citations


@pytest.mark.phase(2)
@pytest.mark.needs("P1", "P2")
def test_revoke_stales_only_dependents(client: TestClient, fire: Fire) -> None:
    """AC-06: admission reports immediate stale fields; inline run then resolves them."""
    require_events("05-revoke-notification")
    admission(fire("01-bootstrap-demo"), "ADMITTED")
    before = {key: latest_result(key)["result_version"] for key in PUBLIC_FIELDS}
    result = admission(fire("05-revoke-notification"), "ADMITTED")
    identifiers = {"notification_number", "responsible_company"}
    assert set(result.stale_fields) == identifiers
    fields = {f.field_key: f for f in read_passport(client, reviewer=True).fields}
    for key in identifiers:
        assert fields[key].verdict == "INSUFFICIENT"
        assert fields[key].freshness == "CURRENT"
        assert rows("SELECT id FROM evidence_requests WHERE case_id=? AND field_key=? AND status='OPEN'", (CASE, key))
    for key in set(PUBLIC_FIELDS) - identifiers:
        assert latest_result(key)["result_version"] == before[key]
    steps = rows("SELECT step, actor, tokens_in, tokens_out, detail FROM trace_steps WHERE run_id=? ORDER BY seq",
                 (latest_run()["id"],))
    assert steps and steps[0]["step"] == "stale:mark"
    assert steps[0]["actor"] == "code"
    assert steps[0]["tokens_in"] == steps[0]["tokens_out"] == 0


@pytest.mark.phase(2)
@pytest.mark.needs("P1", "P2")
def test_volume_change_conflict(client: TestClient, fire: Fire) -> None:
    """AC-09."""
    require_events("04-volume-change")
    admission(fire("01-bootstrap-demo"), "ADMITTED")
    admission(fire("04-volume-change"), "ADMITTED")
    volume = next(f for f in read_passport(client, reviewer=True).fields if f.field_key == "volume")
    assert (volume.verdict, volume.conflict_locus, volume.review_state) == (
        "CONFLICTING", "LISTING_VS_SOURCE", "NEEDS_REVIEW",
    )


@pytest.mark.phase(2)
@pytest.mark.needs("P1", "P2")
def test_prompt_injection_ignored(client: TestClient, fire: Fire) -> None:
    """AC-11: no earlier volume edit in this isolated comparison."""
    require_events("07-injection-listing")
    admission(fire("01-bootstrap-demo"), "ADMITTED")
    before = {f.field_key: (f.verdict, f.conflict_locus) for f in read_passport(client, reviewer=True).fields}
    admission(fire("07-injection-listing"), "ADMITTED")
    after = {f.field_key: (f.verdict, f.conflict_locus) for f in read_passport(client, reviewer=True).fields}
    assert after == before
    assert any(detail.get("ignored_instructions_detected") is True
               for detail in trace_details(latest_run()["id"], "extract"))


@pytest.mark.phase(2)
@pytest.mark.needs("P1", "P2")
def test_unreadable_image(client: TestClient, fire: Fire, tmp_path: Path,
                          monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-12: isolated copy contains only the blurred source, no readable support."""
    require_events("10-blurred-label-photo")
    envelope = event("10-blurred-label-photo")
    snapshot_path = FIXTURES / str(envelope.payload["snapshot"])
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert snapshot["kind"] == "PACKAGING_IMAGE"
    assert all(not passage["text"].strip() for passage in snapshot["passages"])
    source_product = json.loads((FIXTURES / "synthetic/s1-gentle-cleanser/product.json").read_text(encoding="utf-8"))
    isolated = tmp_path / "fixtures/synthetic/isolated"
    isolated.mkdir(parents=True)
    (isolated / "product.json").write_text(json.dumps(source_product, ensure_ascii=False), encoding="utf-8")
    snapshot["version"] = 1
    (isolated / "blurred.v1.json").write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    (isolated / "blurred.v1.png").write_bytes(snapshot_path.with_suffix(".png").read_bytes())
    try:
        with monkeypatch.context() as env:
            env.setenv("FIXTURES_DIR", str(tmp_path / "fixtures"))
            config.reload_settings()
            response = client.post("/api/internal/demo/reset", headers=OPERATOR)
            assert response.is_success
            bootstrap = event("01-bootstrap-demo")
            admission(client.post("/api/internal/events", headers=OPERATOR,
                                  json=bootstrap.model_dump(mode="json")), "ADMITTED")
            assert all(f.verdict == "INSUFFICIENT" for f in read_passport(client, reviewer=True).fields)
            unreadable = rows("SELECT raw_value, readability, quote FROM claims WHERE readability='UNREADABLE'")
            assert unreadable
            assert all(row["raw_value"] is None and row["quote"] is None for row in unreadable)
            requests = rows("SELECT reason FROM evidence_requests WHERE case_id=?", (CASE,))
            assert any("clearer" in row["reason"].lower() and "photo" in row["reason"].lower() for row in requests)
    finally:
        config.reload_settings()


@pytest.mark.phase(2)
@pytest.mark.needs("P1", "P2")
def test_blurred_photo_preserves_readable_evidence(client: TestClient, fire: Fire) -> None:
    require_events("10-blurred-label-photo")
    admission(fire("01-bootstrap-demo"), "ADMITTED")
    before = {f.field_key: f.verdict for f in read_passport(client, reviewer=True).fields}
    admission(fire("10-blurred-label-photo"), "ADMITTED")
    assert {f.field_key: f.verdict for f in read_passport(client, reviewer=True).fields} == before


@pytest.mark.phase(2)
@pytest.mark.needs("P1", "P2")
def test_review_stale_revision_rejected(client: TestClient, fire: Fire) -> None:
    """AC-15: a review is bound to the result and exact case revision."""
    require_events("04-volume-change")
    admission(fire("01-bootstrap-demo"), "ADMITTED")
    old = latest_result("volume")
    admission(fire("04-volume-change"), "ADMITTED")
    before = all_counts()
    response = client.post(f"/api/cases/{CASE}/reviews", headers=REVIEWER, json={
        "result_id": old["id"], "case_revision": old["case_revision"],
        "decision": "APPROVE", "reason": "Review of prior evidence",
    })
    assert response.status_code == 409
    assert all_counts() == before


def request_source_version(request: dict[str, object]) -> str:
    """Find the ID explicitly supplied to the network seam; never guess one."""
    from app.llm.messages import TextPart

    def texts(value: object) -> Iterator[str]:
        if isinstance(value, str):
            yield value
        elif isinstance(value, TextPart):
            yield value.text
        elif isinstance(value, dict):
            for child in value.values():
                yield from texts(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                yield from texts(child)

    visible = " ".join(texts(request))
    candidates = [row["id"] for row in rows("SELECT id FROM source_versions") if row["id"] in visible]
    assert len(candidates) == 1, "Extraction request must identify one stored source version"
    return candidates[0]


def provider_envelope(parsed: BaseModel | None, model: str, *,
                      incomplete: bool = False, refusal: bool = False) -> OpenAIResponse:
    """Installed SDK 3.42 boundary: the provider returns an envelope, not a payload."""
    content = ({"type": "refusal", "refusal": "Declined"} if refusal else
               {"type": "output_text", "text": parsed.model_dump_json() if parsed is not None else "{}", "annotations": []})
    return OpenAIResponse.model_validate({
        "id": "acceptance-response", "object": "response", "created_at": 0, "model": model,
        "status": "incomplete" if incomplete else "completed",
        "incomplete_details": {"reason": "max_output_tokens"} if incomplete else None,
        "output": [{"type": "message", "id": "acceptance-message", "role": "assistant",
                    "status": "completed", "content": [content]}],
        "parallel_tool_calls": False, "tool_choice": "auto", "tools": [],
        "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
                  "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                  "output_tokens_details": {"reasoning_tokens": 0}},
    })


def requested_schema(request: dict[str, object]) -> type[BaseModel]:
    schema = request.get("text_format")
    assert isinstance(schema, type) and issubclass(schema, BaseModel), "Provider request lacks its output schema"
    return schema


def empty_provider_response(request: dict[str, object], extraction_calls: list[str]) -> OpenAIResponse:
    schema = requested_schema(request)
    if issubclass(schema, ClaimExtraction):
        source = request_source_version(request)
        extraction_calls.append(source)
        payload: BaseModel = ClaimExtraction(source_version_id=source, claims=[], ignored_instructions_detected=False)
    else:
        payload = empty_auxiliary_response(schema)
    return provider_envelope(payload, str(request["model"]))


@pytest.mark.phase(2)
@pytest.mark.needs("P1", "P2")
def test_budget_partial(client: TestClient, fire: Fire, monkeypatch: pytest.MonkeyPatch,
                        tmp_path: Path) -> None:
    """AC-17: one shared run budget limits calls at the real provider seam."""
    calls: list[str] = []

    def empty_extraction(**request: object) -> OpenAIResponse:
        return empty_provider_response(request, calls)

    try:
        with monkeypatch.context() as env:
            env.setenv("LLM_MODE", "record")
            env.setenv("MODEL_EXTRACT", "offline-budget-model")
            env.setenv("REPLAY_DIR", str(tmp_path / "recordings"))
            env.setenv("RUN_MAX_MODEL_CALLS", "1")
            env.setenv("AGENT_MAX_TOOL_CALLS", "1")
            env.setattr("app.llm.client._call_api", empty_extraction)
            config.reload_settings()
            admission(fire("01-bootstrap-demo"), "ADMITTED")
            run = latest_run()
            assert run["status"] == "PARTIAL"
            assert run["stop_reason"] == "MODEL_CALL_LIMIT"
            assert len(calls) == 1
            assert all(f.verdict == "INSUFFICIENT" for f in read_passport(client, reviewer=True).fields)
    finally:
        config.reload_settings()


@pytest.mark.phase(2)
@pytest.mark.needs("P1", "P2")
@pytest.mark.parametrize("failure", ["INCOMPLETE", "REFUSAL", "API_ERROR"])
def test_model_failure(client: TestClient, fire: Fire, monkeypatch: pytest.MonkeyPatch,
                       tmp_path: Path, failure: str) -> None:
    """AC-18: provider failure is observable and produces no positive finding."""
    import httpx
    calls: list[str] = []

    def fail_call(**request: object) -> OpenAIResponse:
        calls.append(failure)
        if failure == "API_ERROR":
            raise APIConnectionError(request=httpx.Request("POST", "https://offline.invalid/responses"))
        return provider_envelope(None, str(request["model"]),
                                 incomplete=failure == "INCOMPLETE", refusal=failure == "REFUSAL")

    try:
        with monkeypatch.context() as env:
            env.setenv("LLM_MODE", "record")
            env.setenv("MODEL_EXTRACT", "offline-error-model")
            env.setenv("REPLAY_DIR", str(tmp_path / "recordings"))
            env.setattr("app.llm.client._call_api", fail_call)
            config.reload_settings()
            admission(fire("01-bootstrap-demo"), "ADMITTED")
            run = latest_run()
            assert calls
            assert run["status"] in {"FAILED", "PARTIAL"}
            assert run["error"] or run["stop_reason"]
            buyer = read_passport(client)
            # Failure before any publication may legitimately return no fields.
            assert buyer.run_status == run["status"]
            assert all(f.verdict == "INSUFFICIENT" for f in buyer.fields)
            assert not rows("SELECT id FROM field_results WHERE case_id=? AND verdict!='INSUFFICIENT'", (CASE,))
    finally:
        config.reload_settings()


@pytest.mark.phase(2)
@pytest.mark.needs("P1", "P2")
def test_evidence_added_fulfils_requests(client: TestClient, fire: Fire) -> None:
    require_events("05-revoke-notification", "06-evidence-added")
    admission(fire("01-bootstrap-demo"), "ADMITTED")
    admission(fire("05-revoke-notification"), "ADMITTED")
    requests = rows("SELECT id FROM evidence_requests WHERE case_id=? AND status='OPEN'", (CASE,))
    assert requests
    admission(fire("06-evidence-added"), "ADMITTED")
    fields = {f.field_key: f for f in read_passport(client, reviewer=True).fields}
    assert fields["responsible_company"].verdict == "CONSISTENT"
    assert fields["notification_number"].verdict == "CONFLICTING"
    for request in requests:
        assert rows("SELECT status FROM evidence_requests WHERE id=?", (request["id"],))[0][0] == "FULFILLED"


@pytest.mark.phase(2)
@pytest.mark.needs("P1", "P2")
def test_override_without_citation_rejected(client: TestClient, fire: Fire) -> None:
    """AC-22: reviewer publication is subject to the same citation gate."""
    require_events("04-volume-change")
    admission(fire("01-bootstrap-demo"), "ADMITTED")
    admission(fire("04-volume-change"), "ADMITTED")
    current = latest_result("volume")
    before = all_counts()
    response = client.post(f"/api/cases/{CASE}/reviews", headers=REVIEWER, json={
        "result_id": current["id"], "case_revision": current["case_revision"], "decision": "OVERRIDE",
        "reason": "Citation required", "override": {"verdict": "CONSISTENT", "citations": [],
        "public_text": "50 ml — consistent across the sources checked."},
    })
    assert response.status_code == 422
    assert "NO_CITATION" in response.text
    assert all_counts() == before


@pytest.mark.phase(2)
@pytest.mark.needs("P1", "P2")
def test_private_evidence_filtered(client: TestClient, fire: Fire) -> None:
    """AC-23: no private passage text or URI in buyer evidence/Passport."""
    admission(fire("01-bootstrap-demo"), "ADMITTED")
    private = rows("SELECT p.id, p.text, s.uri FROM passages p "
                   "JOIN source_versions sv ON sv.id=p.source_version_id "
                   "JOIN sources s ON s.id=sv.source_id WHERE s.case_id=? AND s.visibility='PRIVATE'", (CASE,))
    assert private
    buyer = read_passport(client).model_dump_json()
    reviewer = read_passport(client, reviewer=True)
    reviewer_ids = {c.passage_id for f in reviewer.fields for c in f.citations}
    assert reviewer_ids.intersection(row["id"] for row in private)
    for key in ("notification_number", "responsible_company"):
        response = client.get(f"/api/products/{PRODUCT}/fields/{key}/evidence", headers=BUYER)
        assert response.status_code == 200
        buyer += response.text
    for passage in private:
        assert passage["id"] not in buyer
        assert passage["text"] not in buyer
        assert passage["uri"] not in buyer


@pytest.mark.phase(2)
@pytest.mark.needs("P1", "P2")
def test_listing_copy_counts_once(client: TestClient, fire: Fire) -> None:
    """AC-24: copied listing and brand skin claims are one independent family."""
    product_id, _ = bootstrap_named(fire, "13-bootstrap-clear-serum")
    field = next(f for f in read_passport(client, product_id, reviewer=True).fields if f.field_key == "skin_type")
    assert field.verdict == "SINGLE_SOURCE"


@pytest.mark.phase(2)
@pytest.mark.needs("P1", "P2")
def test_claims_audit_uses_policy_trail(client: TestClient, fire: Fire) -> None:
    """AC-27: policy-decided claim findings retain citations and stay in review."""
    product_id, case_id = bootstrap_named(fire, "13-bootstrap-clear-serum")
    findings = rows("SELECT * FROM field_results WHERE case_id=? AND field_key LIKE 'claim:%'", (case_id,))
    assert len(findings) >= 2
    assert sum(row["verdict"] == "CONFLICTING" for row in findings) >= 2
    for finding in findings:
        assert finding["review_state"] == "NEEDS_REVIEW"
        assert finding["policy_version"]
        trail = json.loads(finding["explain_json"])
        assert any(str(step["rule"]).startswith("CL") for step in trail)
        citations = [Citation.model_validate(item) for item in json.loads(finding["citations_json"])]
        assert citations
        for citation in citations:
            check_citation(citation)
    assert all(not f.field_key.startswith("claim:") for f in read_passport(client, product_id).fields)


@pytest.mark.phase(2)
@pytest.mark.needs("P1", "P2")
@pytest.mark.parametrize("mode", ["record", "replay"])
def test_run_deadline_starts_no_model_call(client: TestClient, fire: Fire,
                                          monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mode: str) -> None:
    """AC-41 and AC-17 deadline boundary, no sleeps or clock guesses."""
    try:
        with monkeypatch.context() as env:
            env.setenv("LLM_MODE", mode)
            env.setenv("RUN_DEADLINE_S", "0")
            env.setenv("REPLAY_DIR", str(tmp_path / "no-recordings"))
            config.reload_settings()
            admission(fire("01-bootstrap-demo"), "ADMITTED")
            run = latest_run()
            assert run["status"] == "PARTIAL"
            assert run["stop_reason"] == "RUN_DEADLINE"
            usage = json.loads(run["usage_json"])
            assert usage["model_calls"]["used"] == 0
    finally:
        config.reload_settings()


@pytest.mark.phase(3)
@pytest.mark.needs("P1", "P2")
def test_catalogue_code_scope_without_agent(client: TestClient, fire: Fire) -> None:
    """AC-21 fallback branch: only explicit sizes receive a code scope decision."""
    require_events("09-catalogue-published")
    admission(fire("01-bootstrap-demo"), "ADMITTED")
    admission(fire("09-catalogue-published"), "ADMITTED")
    scopes = rows("SELECT ps.*, p.text, p.locator FROM passage_scopes ps JOIN passages p ON p.id=ps.passage_id "
                  "WHERE ps.run_id=?", (latest_run()["id"],))
    assert scopes
    assert any(row["scope_match"] == "MATCH" and row["decided_by"] == "CODE" for row in scopes)
    assert any(row["scope_match"] == "MISMATCH" and row["decided_by"] == "CODE" for row in scopes)
    assert any(row["scope_match"] == "UNKNOWN" for row in scopes)
    assert not any(row["decided_by"] == "AGENT_VERIFIED" for row in scopes)
    by_locator = {row["locator"]: row for row in scopes}
    assert by_locator["catalogue#50ml"]["scope_match"] == "MATCH"
    assert by_locator["catalogue#100ml"]["scope_match"] == "MISMATCH"
    assert by_locator["catalogue#50ml-skin"]["scope_match"] == "UNKNOWN"


@pytest.mark.phase(3)
@pytest.mark.needs("P1", "P2")
def test_registry_gap_closed(client: TestClient, fire: Fire) -> None:
    """AC-25: code-led registry lookup closes the two identifier gaps."""
    product_id, case_id = bootstrap_named(fire, "12-bootstrap-sun-fluid")
    fields = {f.field_key: f for f in read_passport(client, product_id, reviewer=True).fields}
    for key in ("notification_number", "responsible_company"):
        assert fields[key].verdict == "CONSISTENT"
        assert any(c.source_kind == "REGISTRY_RECORD" for c in fields[key].citations)
    run_id = latest_run(case_id)["id"]
    hops = rows("SELECT step FROM trace_steps WHERE run_id=? AND step LIKE 'gap:hop%'", (run_id,))
    assert 1 <= len(hops) <= 2
    assert any(detail.get("stop_reason") == "GAP_CLOSED" for detail in trace_details(run_id, "gap:stop"))


@pytest.mark.phase(3)
@pytest.mark.needs("P1", "P2")
def test_buyer_explain_filters_internal_details(client: TestClient, fire: Fire) -> None:
    """AC-39 and glass-box ACL: read-only expert detail, buyer-safe projection."""
    admission(fire("01-bootstrap-demo"), "ADMITTED")
    private = rows("SELECT p.text, s.uri FROM passages p JOIN source_versions sv ON sv.id=p.source_version_id "
                   "JOIN sources s ON s.id=sv.source_id WHERE s.visibility='PRIVATE'")
    before = all_counts()
    for key in PUBLIC_FIELDS:
        path = f"/api/products/{PRODUCT}/fields/{key}/explain"
        buyer = client.get(path, headers=BUYER)
        expert = client.get(path, headers=REVIEWER)
        assert buyer.status_code == expert.status_code == 200
        for passage in private:
            assert passage["text"] not in buyer.text
            assert passage["uri"] not in buyer.text
        decision = latest_result(key)
        for step in json.loads(decision["explain_json"]):
            assert step["rule"] not in json.dumps(buyer.json(), ensure_ascii=False).split('"')
        for setting in (config.settings.model_extract, config.settings.model_agent):
            if setting:
                assert setting not in buyer.text
        assert expert.json()
    assert all_counts() == before


@pytest.mark.phase(3)
@pytest.mark.needs("P1", "P2")
@pytest.mark.parametrize("column", ["verdict", "explain_json", "seller_attributable"])
def test_chain_detects_tampering(client: TestClient, fire: Fire, column: str) -> None:
    """AC-35: deliberate DB tampering is the specified test setup."""
    admission(fire("01-bootstrap-demo"), "ADMITTED")
    path = f"/api/cases/{CASE}/chain"
    response = client.get(path, headers=REVIEWER)
    assert response.status_code == 200
    assert response.json()["valid"] is True
    chained = rows("SELECT * FROM field_results WHERE case_id=? ORDER BY chain_seq", (CASE,))
    assert len(chained) >= 2
    target = chained[1]
    changed = {"verdict": "INSUFFICIENT" if target["verdict"] != "INSUFFICIENT" else "UNCERTAIN",
               "explain_json": "[]", "seller_attributable": 1 - int(target["seller_attributable"])}[column]
    with closing(sqlite3.connect(config.settings.db_path)) as db:
        with db:
            db.execute(f"UPDATE field_results SET {column}=? WHERE id=?", (changed, target["id"]))
    broken = client.get(path, headers=REVIEWER)
    assert broken.status_code == 200
    assert broken.json()["valid"] is False
    assert broken.json()["broken_at"] == target["chain_seq"]


@pytest.mark.phase(3)
@pytest.mark.needs("P1", "P2")
def test_search_bm25_is_read_only(client: TestClient, fire: Fire) -> None:
    """AC-32: explicit BM25 mode gives ranked passages, never a new finding."""
    admission(fire("01-bootstrap-demo"), "ADMITTED")
    before = [tuple(row) for row in rows("SELECT * FROM field_results ORDER BY id")]
    response = client.get(f"/api/cases/{CASE}/search", params={"q": "Niacinamide", "mode": "bm25"}, headers=REVIEWER)
    assert response.status_code == 200
    payload = response.json()
    assert payload["hits"]
    assert payload["stages"]["bm25"]
    assert [tuple(row) for row in rows("SELECT * FROM field_results ORDER BY id")] == before
    denied = client.get(f"/api/cases/{CASE}/search", params={"q": "Niacinamide"}, headers=BUYER)
    assert denied.status_code == 403


@pytest.mark.phase(4)
@pytest.mark.needs("P1", "P2")
def test_receipt_preserves_purchase_then_reports_revoke(client: TestClient, fire: Fire) -> None:
    """AC-30: fresh DB, order BEFORE the first revoke; never reuse processed event 05."""
    require_events("05-revoke-notification")
    admission(fire("01-bootstrap-demo"), "ADMITTED")
    purchased = read_passport(client).model_dump(mode="json")
    response = client.post("/api/orders", headers=BUYER, json={"product_id": PRODUCT})
    assert response.is_success
    orders = rows("SELECT * FROM orders WHERE case_id=?", (CASE,))
    assert len(orders) == 1
    receipt = orders[0]
    assert json.loads(receipt["snapshot_json"]) == purchased
    assert receipt["snapshot_hash"]
    admission(fire("05-revoke-notification"), "ADMITTED")
    after = rows("SELECT * FROM orders WHERE id=?", (receipt["id"],))[0]
    assert tuple(after) == tuple(receipt)
    fetched = client.get(f"/api/orders/{receipt['id']}", headers=BUYER)
    assert fetched.status_code == 200
    payload = fetched.json()
    assert payload["changed_since_purchase"] is True
    # Compare the documented persisted receipt with current public field states;
    # the future route's per-field diff encoding is not yet a frozen DTO.
    then = {field["field_key"]: (field["verdict"], field["freshness"]) for field in purchased["fields"]}
    changed = {field.field_key for field in read_passport(client).fields
               if (field.verdict, field.freshness) != then[field.field_key]}
    assert changed == {"notification_number", "responsible_company"}
    before_duplicate = all_counts()
    admission(fire("05-revoke-notification"), "DUPLICATE")
    assert all_counts() == before_duplicate


@pytest.mark.phase(4)
@pytest.mark.needs("P1", "P2")
def test_marketplace_clusters_without_changing_passport(client: TestClient, fire: Fire,
                                                        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """AC-34: planted synthetic five-shop pattern, never an assumption about R5 pages."""
    root = tmp_path / "fixtures"
    shutil.copytree(FIXTURES / "synthetic/s1-gentle-cleanser", root / "synthetic/product")
    shutil.copytree(FIXTURES / "events", root / "events")
    marketplace = root / "marketplace" / PRODUCT
    marketplace.mkdir(parents=True)
    copied = "Dung tích được công bố trên gian hàng: 50 ml cho một chai sản phẩm trong danh mục."
    descriptions = [copied, copied, copied,
                    "Thông số thể tích của mỗi đơn vị bán lẻ là 50 ml; thông tin riêng từ bên cung cấp thứ tư.",
                    "Bảng đặc tả ở quầy hàng thứ năm ghi thể tích đóng chai 75 ml, thuộc lô hàng đang trưng bày."]
    for index, description in enumerate(descriptions):
        snapshot = {"source_id": f"acceptance-shop-{index}", "kind": "LISTING", "product_id": PRODUCT,
                    "version": 1, "uri": f"demo://marketplace/{index}", "captured_at": "2026-10-31T03:00:00Z",
                    "dataset_origin": "SYNTHETIC", "visibility": "PUBLIC", "family": f"seller:acceptance-{index}",
                    "status": "ACTIVE", "shop_name": f"Independent test shop {index}",
                    "scope": {"product": PRODUCT, "variant": "50ml", "market": "VN", "version": "1"},
                    "passages": [{"id": f"shop-passage-{index}", "locator": "specs#volume",
                                  "section": "specifications", "text": description}]}
        (marketplace / f"shop-{index}.json").write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    try:
        with monkeypatch.context() as env:
            env.setenv("FIXTURES_DIR", str(root))
            config.reload_settings()
            assert client.post("/api/internal/demo/reset", headers=OPERATOR).is_success
            admission(fire("01-bootstrap-demo"), "ADMITTED")
            before = read_passport(client).model_dump(mode="json")
            response = client.post(f"/api/internal/marketplace/{PRODUCT}/scan", headers=OPERATOR)
            assert response.is_success
            findings = rows("SELECT * FROM marketplace_findings WHERE product_id=? AND field_key='volume'", (PRODUCT,))
            assert len({row["cluster"] for row in findings}) == 3
            assert sum(bool(row["outlier"]) for row in findings) == 1
            assert read_passport(client).model_dump(mode="json") == before
            buyer = client.get(f"/api/products/{PRODUCT}/marketplace", headers=BUYER)
            assert buyer.status_code == 200
            for finding in findings:
                assert finding["shop"] not in buyer.text
    finally:
        config.reload_settings()


@pytest.mark.phase(2)
@pytest.mark.needs("P1", "P2")
def test_replay_model_change_is_a_miss(client: TestClient, fire: Fire,
                                      monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """AC-38: empty replay directory cannot reuse another model or call the network."""
    try:
        with monkeypatch.context() as env:
            env.setenv("LLM_MODE", "replay")
            env.setenv("MODEL_EXTRACT", "different-unrecorded-model")
            env.setenv("REPLAY_DIR", str(tmp_path / "empty-replay"))
            config.reload_settings()
            admission(fire("01-bootstrap-demo"), "ADMITTED")
            run = latest_run()
            assert run["status"] in {"FAILED", "PARTIAL"}
            diagnostic = str(run["error"]) + str(run["stop_reason"]) + json.dumps(trace_details(run["id"]))
            assert "REPLAY_MISS" in diagnostic
    finally:
        config.reload_settings()


@pytest.mark.phase(2)
@pytest.mark.needs("P1", "P2")
def test_whole_available_story_preserves_publication_invariants(client: TestClient, fire: Fire) -> None:
    """AC-19/20 expanded to the complete phase-2 story, retaining Stage-A checks."""
    sequence = ("01-bootstrap-demo", "05-revoke-notification", "06-evidence-added",
                "04-volume-change", "07-injection-listing", "10-blurred-label-photo",
                "11-bootstrap-hydra", "13-bootstrap-clear-serum")
    require_events(*sequence)
    for name in sequence:
        admission(fire(name), "ADMITTED")
        product_id = str(event(name).payload["product_id"])
        passport = read_passport(client, product_id, reviewer=True)
        assert len(passport.fields) == len(PUBLIC_FIELDS)
        for field in passport.fields:
            assert not FORBIDDEN.search(field.public_text)
            if field.verdict != "INSUFFICIENT":
                assert field.citations
            for citation in field.citations:
                check_citation(citation)


@dataclass
class WebScenario:
    brand: str
    product_name: str
    url: str
    identity: bool = True
    queries: list[str] = data_field(default_factory=list)
    urls: list[str] = data_field(default_factory=list)


@pytest.fixture
def web_scenario(client: TestClient, monkeypatch: pytest.MonkeyPatch,
                 tmp_path: Path) -> Iterator[WebScenario]:
    """Replace only P2's documented search/fetch provider, never discovery/policy."""
    provider = import_module("app.connectors.websearch")
    folder = tmp_path / "fixtures/synthetic/web-product"
    shutil.copytree(FIXTURES / "synthetic/s1-gentle-cleanser", folder)
    product_path = folder / "product.json"
    product = json.loads(product_path.read_text(encoding="utf-8"))
    product["web"] = {"enabled": True, "brand_domains": ["brand.example"], "aliases": [product["name"]]}
    product_path.write_text(json.dumps(product, ensure_ascii=False), encoding="utf-8")
    url = "https://www.pharmacity.vn/acceptance-item.html"
    calls = WebScenario(brand=product["brand"], product_name=product["name"], url=url)

    def search(query: str, *, allowed_domains: list[str], country: str) -> list[object]:
        calls.queries.append(query)
        return [provider.Result(url=url, title=product["name"],
                                snippet=f"{product['name']} 75 ml", domain="pharmacity.vn")]

    def fetch(url: str) -> object:
        calls.urls.append(url)
        assert url == calls.url, "Code tried to fetch a URL outside actual search results"
        name = product["name"] if calls.identity else "Unrelated catalogue entry"
        return provider.Page(url=url, status=200, text=f"{name}. Dung tích: 75 ml. Nội dung catalogue bán lẻ.",
                             fetched_at="2026-10-31T03:00:00Z")

    try:
        with monkeypatch.context() as env:
            env.setenv("FIXTURES_DIR", str(tmp_path / "fixtures"))
            env.setenv("WEB_SEARCH", "on")
            env.setattr(provider, "search", search)
            env.setattr(provider, "fetch", fetch)
            config.reload_settings()
            reset = client.post("/api/internal/demo/reset", headers=OPERATOR)
            assert reset.is_success
            yield calls
    finally:
        config.reload_settings()


def bootstrap_web(client: TestClient) -> None:
    admission(client.post("/api/internal/events", headers=OPERATOR,
                          json=event("01-bootstrap-demo").model_dump(mode="json")), "ADMITTED")


@pytest.mark.phase(4)
@pytest.mark.needs("P1", "P2")
def test_retailer_disagreement_never_blames_seller(client: TestClient, web_scenario: WebScenario) -> None:
    """AC-26: listing/label 50 ml versus fetched retailer 75 ml, offline provider."""
    bootstrap_web(client)
    sources = rows("SELECT s.kind, s.dataset_origin, sv.sha256 FROM sources s "
                   "JOIN source_versions sv ON sv.source_id=s.id WHERE s.uri=?", (web_scenario.url,))
    assert sources
    assert all(s["kind"] == "WEB_PAGE" and s["dataset_origin"] == "REAL" and len(s["sha256"]) == 64 for s in sources)
    volume = latest_result("volume")
    assert volume["seller_attributable"] == 0
    assert volume["conflict_locus"] != "LISTING_VS_SOURCE"
    assert volume["review_state"] == "NEEDS_REVIEW"
    before = all_counts()
    searches = len(web_scenario.queries)
    for _ in range(3):
        read_passport(client)
    assert len(web_scenario.queries) == searches
    assert all_counts() == before


@pytest.mark.phase(4)
@pytest.mark.needs("P1", "P2")
def test_web_queries_and_fetches_are_bounded(client: TestClient, web_scenario: WebScenario) -> None:
    """AC-26b: verify actual tool arguments, not model assertions about them."""
    bootstrap_web(client)
    queries = web_scenario.queries
    assert 1 <= len(queries) <= config.settings.web_max_searches
    assert len(queries) == len(set(queries))
    assert all(web_scenario.brand.casefold() in query.casefold() for query in queries)
    assert 1 <= len(web_scenario.urls) <= config.settings.web_max_pages
    assert set(web_scenario.urls) == {web_scenario.url}
    assert rows("SELECT id FROM web_searches WHERE case_id=?", (CASE,))


@pytest.mark.phase(4)
@pytest.mark.needs("P1", "P2")
def test_web_without_identity_is_confirm_only(client: TestClient, web_scenario: WebScenario) -> None:
    """AC-36: no product alias in fetched text cannot create seller conflict."""
    web_scenario.identity = False
    bootstrap_web(client)
    versions = rows("SELECT s.kind, sv.scope_json FROM sources s JOIN source_versions sv ON sv.source_id=s.id "
                    "WHERE s.uri=?", (web_scenario.url,))
    # Dropping an unidentified page entirely is also a valid stricter outcome.
    for version in versions:
        assert version["kind"] != "BRAND_PAGE"
        assert json.loads(version["scope_json"])["identity_verified"] is False
    assert latest_result("volume")["seller_attributable"] == 0
    assert latest_result("volume")["conflict_locus"] != "LISTING_VS_SOURCE"


def copy_database(source: Path, destination: Path) -> None:
    """Test setup only: restore the same source identities before replay."""
    with closing(sqlite3.connect(source)) as original, closing(sqlite3.connect(destination)) as target:
        original.backup(target)


def semantic_passport(client: TestClient) -> list[tuple[str, str, str | None, str]]:
    passport = read_passport(client, reviewer=True)
    assert {f.field_key for f in passport.fields} == set(PUBLIC_FIELDS)
    return sorted((f.field_key, f.verdict, f.conflict_locus, f.freshness) for f in passport.fields)


@pytest.mark.phase(2)
@pytest.mark.needs("P1", "P2")
@pytest.mark.parametrize("second_model", ["offline-record-model", "unrecorded-other-model"])
def test_record_replay_story_and_model_isolation(client: TestClient, fire: Fire,
                                                 monkeypatch: pytest.MonkeyPatch,
                                                 tmp_path: Path, second_model: str) -> None:
    """AC-28/38: real record/replay implementation, only network response replaced."""
    start = tmp_path / "before-record.db"
    copy_database(config.settings.db_path, start)
    calls: list[str] = []

    def empty_response(**request: object) -> OpenAIResponse:
        return empty_provider_response(request, calls)

    try:
        with monkeypatch.context() as env:
            env.setenv("REPLAY_DIR", str(tmp_path / "recordings"))
            env.setenv("MODEL_EXTRACT", "offline-record-model")
            env.setenv("LLM_MODE", "record")
            env.setattr("app.llm.client._call_api", empty_response)
            config.reload_settings()
            run_story(fire)
            expected = semantic_passport(client)
            assert latest_run()["status"] in {"COMPLETED", "WAITING_EVIDENCE", "WAITING_REVIEW"}
            assert calls
            assert list((tmp_path / "recordings").rglob("*.json"))
            copy_database(start, config.settings.db_path)
            before_replay_calls = len(calls)
            env.setenv("LLM_MODE", "replay")
            env.setenv("MODEL_EXTRACT", second_model)
            config.reload_settings()
            run_story(fire)
            assert len(calls) == before_replay_calls
            run = latest_run()
            if second_model == "offline-record-model":
                assert semantic_passport(client) == expected
                assert run["status"] in {"COMPLETED", "WAITING_EVIDENCE", "WAITING_REVIEW"}
                assert run["llm_mode"] == "REPLAY"
                assert json.loads(run["usage_json"])["model_calls"]["used"] > 0
                assert read_passport(client).dataset_origin == "SYNTHETIC"
            else:
                assert run["status"] in {"FAILED", "PARTIAL"}
                diagnostic = str(run["error"]) + str(run["stop_reason"]) + json.dumps(trace_details(run["id"]))
                assert "REPLAY_MISS" in diagnostic
    finally:
        config.reload_settings()


def extracted(field_key: str, passage: sqlite3.Row, quote: str) -> ExtractedClaim:
    return ExtractedClaim(
        field_key=field_key, raw_value=quote, passage_id=passage["id"], quote=quote,
        readability="READABLE", proposed_skin_types=None, proposed_ingredients=None, proposed_volume_ml=None,
    )


@pytest.mark.phase(2)
@pytest.mark.needs("P1", "P2")
def test_coverage_retry_once_then_cached(client: TestClient, fire: Fire,
                                        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """AC-37: intentionally omit one explicit volume, then answer the targeted retry."""
    calls: dict[str, int] = {}
    listing_id = rows("SELECT sv.id FROM source_versions sv JOIN sources s ON s.id=sv.source_id "
                      "WHERE s.case_id=? AND s.kind='LISTING'", (CASE,))[0][0]

    def omit_then_answer(**request: object) -> OpenAIResponse:
        schema = requested_schema(request)
        if not issubclass(schema, ClaimExtraction):
            return provider_envelope(empty_auxiliary_response(schema), str(request["model"]))
        source_id = request_source_version(request)
        calls[source_id] = calls.get(source_id, 0) + 1
        claims: list[ExtractedClaim] = []
        if source_id == listing_id and calls[source_id] > 1:
            for passage in rows("SELECT * FROM passages WHERE source_version_id=?", (source_id,)):
                match = re.search(r"\b\d+(?:[.,]\d+)?\s*ml\b", passage["text"], re.IGNORECASE)
                if match:
                    claims.append(extracted("volume", passage, match.group(0)))
        return provider_envelope(ClaimExtraction(source_version_id=source_id, claims=claims, ignored_instructions_detected=False),
                                 str(request["model"]))

    try:
        with monkeypatch.context() as env:
            env.setenv("LLM_MODE", "record")
            env.setenv("MODEL_EXTRACT", "offline-retry-model")
            env.setenv("REPLAY_DIR", str(tmp_path / "recordings"))
            env.setattr("app.llm.client._call_api", omit_then_answer)
            config.reload_settings()
            admission(fire("01-bootstrap-demo"), "ADMITTED")
            assert calls[listing_id] == 2
            assert all(count <= 2 for count in calls.values())
            assert rows("SELECT id FROM claims WHERE source_version_id=? AND field_key='volume'", (listing_id,))
            before = dict(calls)
            envelope = event("01-bootstrap-demo")
            envelope.event_id += "-cached"
            envelope.idempotency_key += "-cached"
            admission(client.post("/api/internal/events", headers=OPERATOR,
                                  json=envelope.model_dump(mode="json")), "ADMITTED")
            assert calls == before
    finally:
        config.reload_settings()


def typed_proposal_response(schema: type[BaseModel], proposal: dict[str, str | None]) -> BaseModel:
    """Use the supplied schema's list envelope; do not invent its class/key name."""
    shape = schema.model_json_schema()
    if shape.get("type") == "array":
        return schema.model_validate([proposal])
    properties = shape.get("properties", {})
    arrays = [name for name, spec in properties.items() if spec.get("type") == "array"]
    assert len(arrays) == 1 and set(shape.get("required", [])) <= set(arrays), (
        "P2 scope response must expose its documented proposal list", schema.__name__,
    )
    return schema.model_validate({arrays[0]: [proposal]})


def schema_has_scope_proposal(schema: type[BaseModel]) -> bool:
    shape = schema.model_json_schema()
    definitions = [shape, *shape.get("$defs", {}).values()]
    return any({"passage_id", "applies", "anchor_passage_id", "reason"} <= set(item.get("properties", {}))
               for item in definitions)


def empty_auxiliary_response(schema: type[BaseModel]) -> BaseModel:
    """Canon/audit produce no proposals for this known-vocabulary scope scenario."""
    shape = schema.model_json_schema()
    if shape.get("type") == "array":
        return schema.model_validate([])
    values: dict[str, object] = {}
    for name in shape.get("required", []):
        spec = shape["properties"][name]
        if spec.get("type") == "array":
            values[name] = []
        elif spec.get("type") == "boolean":
            values[name] = False
        elif any(option.get("type") == "null" for option in spec.get("anyOf", [])):
            values[name] = None
        else:
            raise AssertionError(f"Auxiliary output needs a typed scenario response: {schema.__name__}.{name}")
    return schema.model_validate(values)


@pytest.mark.phase(3)
@pytest.mark.needs("P1", "P2")
@pytest.mark.parametrize("valid_anchor", [True, False])
def test_scope_anchor_changes_verdict_only_after_code_validation(
    client: TestClient, fire: Fire, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, valid_anchor: bool,
) -> None:
    """AC-40 plus AC-21: fake model proposes; real scope validation/policy publishes."""
    require_events("09-catalogue-published")
    admission(fire("01-bootstrap-demo"), "ADMITTED")
    before = latest_result("skin_type")["verdict"]
    assert before == "SINGLE_SOURCE"
    proposals: list[dict[str, str | None]] = []

    def provider_response(**request: object) -> OpenAIResponse:
        schema = requested_schema(request)
        if issubclass(schema, ClaimExtraction):
            source_id = request_source_version(request)
            claims = [ExtractedClaim(
                field_key=row["field_key"], raw_value=row["raw_value"], passage_id=row["passage_id"],
                quote=row["quote"], readability=row["readability"], proposed_skin_types=None,
                proposed_ingredients=None, proposed_volume_ml=None,
            ) for row in rows("SELECT * FROM claims WHERE source_version_id=?", (source_id,))]
            if not claims:
                for passage in rows("SELECT * FROM passages WHERE source_version_id=?", (source_id,)):
                    volume = re.search(r"\b\d+\s*ml\b", passage["text"], re.IGNORECASE)
                    if volume:
                        claims.append(extracted("volume", passage, volume.group(0)))
                    if passage["locator"] == "catalogue#50ml-skin":
                        claims.append(extracted("skin_type", passage, passage["text"]))
            return provider_envelope(ClaimExtraction(source_version_id=source_id, claims=claims,
                                                     ignored_instructions_detected=False), str(request["model"]))
        if not schema_has_scope_proposal(schema):
            return provider_envelope(empty_auxiliary_response(schema), str(request["model"]))
        target = rows("SELECT id FROM passages WHERE locator='catalogue#50ml-skin'")
        anchor_locator = "catalogue#50ml" if valid_anchor else "catalogue#100ml"
        anchor = rows("SELECT id FROM passages WHERE locator=?", (anchor_locator,))
        assert len(target) == len(anchor) == 1
        proposal = {"passage_id": target[0]["id"], "applies": "YES",
                    "anchor_passage_id": anchor[0]["id"], "reason": "Place the size-less line under the supplied heading"}
        proposals.append(proposal)
        return provider_envelope(typed_proposal_response(schema, proposal), str(request["model"]))

    try:
        with monkeypatch.context() as env:
            env.setenv("LLM_MODE", "record")
            env.setenv("MODEL_EXTRACT", "offline-anchor-extract")
            env.setenv("MODEL_AGENT", "offline-anchor-proposal")
            env.setenv("REPLAY_DIR", str(tmp_path / "recordings"))
            env.setattr("app.llm.client._call_api", provider_response)
            config.reload_settings()
            admission(fire("09-catalogue-published"), "ADMITTED")
            assert proposals
            target_id = proposals[-1]["passage_id"]
            placement = rows("SELECT * FROM passage_scopes WHERE passage_id=?", (target_id,))
            assert placement
            result = latest_result("skin_type")
            citations = json.loads(result["citations_json"])
            assert target_id in {citation["passage_id"] for citation in citations}
            if valid_anchor:
                assert placement[-1]["scope_match"] == "MATCH"
                assert placement[-1]["decided_by"] == "AGENT_VERIFIED"
                assert result["verdict"] == "CONSISTENT"
                assert result["review_state"] != "NEEDS_REVIEW"
                assert any("before" in detail and "after" in detail
                           for detail in trace_details(latest_run()["id"], "agent:effect"))
            else:
                assert placement[-1]["scope_match"] == "AGENT"
                assert result["review_state"] == "NEEDS_REVIEW"
    finally:
        config.reload_settings()


@pytest.mark.phase(2)
@pytest.mark.needs("P1", "P2", "P4")
def test_eval_reports_baseline_and_gold_status(tmp_path: Path) -> None:
    """AC-29: next-phase evaluator smoke, no expected score from candidate output."""
    import os
    output = tmp_path / "evaluation"
    environment = {**os.environ, "LLM_MODE": "fallback", "WORKER_INLINE": "1", "OCR_ENABLED": "0",
                   "WEB_SEARCH": "off", "DB_PATH": str(tmp_path / "evaluation.db"),
                   "AGENTS_TRACING": "0", "OPENAI_AGENTS_DISABLE_TRACING": "1"}
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/eval.py"), "--limit-checkpoints", "2", "--output-dir", str(output)],
        cwd=ROOT, env=environment, capture_output=True, text=True, encoding="utf-8", timeout=15, check=False,
    )
    assert result.returncode == 0, result.stderr
    report = (output / "eval-latest.md").read_text(encoding="utf-8")
    payload = json.loads((output / "eval-latest.json").read_text(encoding="utf-8"))
    assert payload
    assert "B0" in report and "candidate" in report.lower()
    assert "fallback" in report.lower()
    # Only inspect the label's declared review state, never use its verdicts here.
    gold = json.loads((FIXTURES / "gold/dev/demo-story.json").read_text(encoding="utf-8"))
    assert gold["status"] in report
