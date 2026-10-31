"""Independent HTTP/read-only-state doubles for the P4 S2 story verifier."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.models import PUBLIC_FIELDS
from scripts.sync_check import CaseState, StoredField, run_phase_two


def field(key: str, verdict: str = "CONSISTENT", *, version: int = 1,
          locus: str | None = None, seller: bool = False) -> StoredField:
    return StoredField(id=f"arbitrary-{key}-{version}", field_key=key, result_version=version,
        case_revision=version, verdict=verdict, conflict_locus=locus, review_state="NEEDS_REVIEW",
        seller_attributable=seller, citations_json='[{"passage_id":"stored-evidence"}]',
        explain_json='[{"rule":"CL-test"}]')


@pytest.mark.parametrize("mode", ["fallback", "replay"])
@pytest.mark.parametrize("fault", [None, "collateral", "stale-model", "requests", "fulfillment", "volume",
    "review-binding", "review-history", "stale-http", "stale-write", "injection", "unreadable", "erased",
    "seller", "audit", "buyer-leak", "mode", "RUNNING", "QUEUED", "CANCELLED", "no-job",
    "no-run", "wrong-case", "unlinked"])
def test_s2_harness_detects_lifecycle_contract_failures(mode: str, fault: str | None) -> None:
    event = "bootstrap"
    revision = 1
    writes = 0
    reviews: list[dict[str, object]] = []
    fired: list[str] = []
    base = {key: field(key) for key in PUBLIC_FIELDS}
    current = base.copy()

    def state(case: str) -> CaseState:
        if case == "other-case":
            hydra = base.copy()
            for key in ("skin_type", "key_ingredients"):
                hydra[key] = field(key, "CONFLICTING", locus="WITHIN_SOURCE", seller=fault == "seller")
            return CaseState(1, hydra, True, True, True)
        if case == "claim-case":
            claims = base.copy()
            if fault != "audit":
                claims.update({key: field(key, "CONFLICTING") for key in ("claim:free_from:a", "claim:free_from:b")})
            return CaseState(1, claims, True, True, True)
        output = current.copy()
        if event == "05-revoke-notification" and fault == "collateral":
            output["volume"] = field("volume", version=7)
        if event == "10-blurred-label-photo" and fault == "erased":
            output["volume"] = field("volume", "INSUFFICIENT")
        return CaseState(revision, output, fault != "stale-model", fault != "injection", fault != "unreadable")

    def passport(case: str, product: str, buyer: bool = False) -> dict[str, object]:
        fields = []
        for item in state(case).fields.values():
            if item.field_key.startswith("claim:") and buyer and fault != "buyer-leak":
                continue
            fields.append({"field_key": item.field_key, "verdict": item.verdict,
                "label": "Conflict in source" if item.conflict_locus == "WITHIN_SOURCE" else "Observed",
                "public_text": "Source comparison", "conflict_locus": item.conflict_locus,
                "freshness": "CURRENT", "review_state": item.review_state, "checked_at": None,
                "citations": [{"passage_id": passage, "source_kind": "BRAND_PAGE", "source_version": 1,
                               "locator": "section", "excerpt": "Source comparison"} for passage in ("a", "b")]})
        return {"product_id": product, "dataset_origin": "SYNTHETIC", "last_checked_at": None,
                "run_status": "COMPLETED", "fields": fields, "disclaimer": "Sources checked."}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal event, current, revision, writes
        path = request.url.path
        if "/fire/" in path:
            event = path.rsplit("/", 1)[1]
            fired.append(event)
            revision += 1
            if event == "05-revoke-notification":
                for key in ("notification_number", "responsible_company"):
                    current[key] = field(key, "INSUFFICIENT", version=revision)
            elif event == "06-evidence-added":
                current["notification_number"] = field("notification_number", "CONFLICTING", version=revision)
                current["responsible_company"] = field("responsible_company", version=revision)
            elif event == "04-volume-change":
                current["volume"] = field("volume", "CONSISTENT" if fault == "volume" else "CONFLICTING",
                                          version=revision, locus="LISTING_VS_SOURCE")
            elif event == "07-injection-listing":
                current["volume"] = field("volume", version=revision)
            return httpx.Response(200, json={"event_id": event, "outcome": "ADMITTED", "reason": "test",
                "job_id": None if fault == "no-job" else "job",
                "stale_fields": ["notification_number", "responsible_company"]})
        if path.endswith("passport"):
            product = path.split("/")[3]
            case = {"main-product": "main-case", "other-product": "other-case", "claim-product": "claim-case"}[product]
            return httpx.Response(200, json=passport(case, product, request.headers["X-Demo-Role"] == "BUYER"))
        if path.endswith("history"):
            requests = [{"id": key, "case_id": "main-case", "field_key": key, "gap_id": "gap",
                "reason": "missing document", "requested_from": "SELLER", "created_at": "2026-10-31T05:00:00Z",
                "status": "OPEN" if event == "05-revoke-notification" or fault == "fulfillment" else "FULFILLED"}
                for key in ("notification_number", "responsible_company")]
            return httpx.Response(200, json={"case_id": "main-case", "case_revision": revision,
                "results": [], "events": [], "reviews": [] if fault == "review-history" else reviews,
                "requests": [] if fault == "requests" else requests})
        if path.endswith("reviews"):
            body = json.loads(request.content)
            if body["case_revision"] != revision:
                if fault == "stale-write":
                    writes += 1
                return httpx.Response(200 if fault == "stale-http" else 409, json={})
            review = {**body, "id": "review-id", "case_id": "main-case", "reviewer_id": "reviewer",
                      "override": None, "created_at": "2026-10-31T05:00:00Z", "review_state": "REVIEWED"}
            if fault == "review-binding":
                review["result_id"] = "wrong-result"
            reviews.append(review)
            return httpx.Response(200, json=review)
        if path.endswith("runs"):
            return httpx.Response(200, json=[{"id": "run-" + fired_event,
                "case_id": "wrong" if fault == "wrong-case" else {"11-bootstrap-hydra": "other-case", "13-bootstrap-clear-serum": "claim-case"}.get(fired_event, "main-case"), "case_revision": revision,
                "trigger_event_id": fired_event, "status": fault if fault in {"RUNNING", "QUEUED", "CANCELLED"} else "COMPLETED", "stop_reason": None,
                "llm_mode": ("REPLAY" if mode == "fallback" else "FALLBACK") if fault == "mode" else mode.upper(),
                "started_at": None, "finished_at": None, "usage": {"model_calls": 0, "tokens_in": 0, "tokens_out": 0}}
                for fired_event in ([] if fault == "no-run" else fired)])
        if path.endswith("events/log"):
            return httpx.Response(200, json=[{"event_id": fired_event, "outcome": "ADMITTED", "reason": "test",
                "job_id": "job", "stale_fields": [], "received_at": "2026-10-31T05:00:00Z",
                "run_id": "other" if fault == "unlinked" else "run-" + fired_event} for fired_event in fired])
        raise AssertionError(path)

    with httpx.Client(transport=httpx.MockTransport(handler), base_url="http://test") as client:
        result = run_phase_two(client, state, lambda: {"reviews": writes}, "main-product", "main-case",
                               "other-product", "other-case", "claim-product", "claim-case", expected_mode=mode)
    assert any(check.status == "FAIL" for check in result) == (fault is not None)
    if fault is None:
        assert len(result) == 9 and result[-1].name == "S2 run modes"
