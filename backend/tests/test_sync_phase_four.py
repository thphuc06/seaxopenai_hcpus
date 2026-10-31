"""S4 operational verifier exercised through independent HTTP transport doubles."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import httpx
import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.models import PUBLIC_FIELDS
from scripts.sync_check import CheckFailure, check_receipt, check_marketplace, check_web_audit


class Story:
    def __init__(self, mode: str, fault: str | None = None, product: str = "unrelated-137") -> None:
        self.mode, self.fault, self.product = mode, fault, product
        self.case = "different-case"
        self.events: list[str] = []
        self.writes = 0
        self.created: dict[str, object] | None = None

    def passport(self, revoked: bool = False) -> dict[str, object]:
        return dict(product_id="different-product" if self.fault == "wrong-product" else self.product, dataset_origin="SYNTHETIC", last_checked_at=None,
            run_status="COMPLETED", disclaimer="Evidence only", fields=[dict(field_key=key,
                label="Not verified" if revoked and key in {"notification_number", "responsible_company"} else "Single source",
                public_text="Stored evidence", verdict="INSUFFICIENT" if revoked and key in {"notification_number", "responsible_company"} else "SINGLE_SOURCE",
                freshness="CURRENT", conflict_locus=None, review_state="AUTO_DRAFT", checked_at=None, citations=[]) for key in PUBLIC_FIELDS])

    def count(self) -> dict[str, int]:
        return {"writes": self.writes}

    def stored(self, receipt_id: str) -> tuple[str, str]:
        raw = json.dumps(self.passport(), sort_keys=True, ensure_ascii=False)
        if self.fault == "stored-rewrite" and "05-revoke-notification" in self.events:
            raw = json.dumps(self.passport(True), sort_keys=True, ensure_ascii=False)
        return raw, hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def receipt(self) -> dict[str, object]:
        revoked = "05-revoke-notification" in self.events
        snapshot, current = self.passport(), self.passport(revoked)
        data = dict(id="receipt-variant", product_id=self.product, case_id=self.case, placed_at="2026-10-31T03:00:00Z",
                    case_revision=1, snapshot=snapshot, snapshot_hash="garbage" if self.fault == "lying-hash" else self.stored("receipt-variant")[1], chain_head="b" * 64,
                    hash_valid=self.fault != "hash", changed_since_purchase=revoked,
                    diff=[dict(field_key=old["field_key"], then=old, now=new, changed=old != new)
                          for old, new in zip(snapshot["fields"], current["fields"])])
        if revoked:
            if self.fault == "rewrite":
                data["snapshot"] = current
            if self.fault == "revision":
                data["case_revision"] = 2
            if self.fault == "collateral":
                data["diff"][0]["changed"] = True
            if self.fault == "omit":
                data["diff"].pop()
            if self.fault == "wrong-now":
                data["diff"][-1]["now"] = deepcopy(data["diff"][-1]["then"])
        return data

    def handle(self, request: httpx.Request) -> httpx.Response:
        path, method = request.url.path, request.method
        if path.endswith("/reset"):
            self.events.clear()
            self.writes = 0
            return httpx.Response(200, json={})
        if "/demo/fire/" in path:
            name = path.rsplit("/", 1)[1]
            duplicate = name in self.events
            if not duplicate:
                self.events.append(name)
            if duplicate and self.fault == "duplicate":
                self.writes += 1
            return httpx.Response(200, json=dict(event_id=name, outcome="DUPLICATE" if duplicate else "ADMITTED",
                reason="test", job_id=None if self.fault == "no-job" else "job-"+name, stale_fields=[]))
        if path.endswith("/runs"):
            return httpx.Response(200, json=[dict(id="run-"+event, case_id=self.case, case_revision=1,
                trigger_event_id=event, status="PARTIAL" if self.fault == "partial" else "COMPLETED",
                stop_reason=None, llm_mode="LIVE" if self.fault == "mode" else self.mode.upper(), started_at=None,
                finished_at=None, usage=dict(model_calls=0,tokens_in=0,tokens_out=0)) for event in self.events])
        if path.endswith("/events/log"):
            return httpx.Response(200, json=[dict(event_id=event, outcome="ADMITTED", reason="test", job_id="job-"+event,
                stale_fields=[], received_at="2026-10-31T03:00:00Z",run_id="wrong" if self.fault == "unlinked" else "run-"+event)
                for event in self.events])
        if path.endswith("/passport"):
            return httpx.Response(200, json=self.passport("05-revoke-notification" in self.events))
        if path == "/api/orders" and method == "POST":
            if self.fault == "stub":
                return httpx.Response(501, json={})
            self.created = self.receipt()
            return httpx.Response(200, json=self.created)
        if path.startswith("/api/orders"):
            if self.fault == "read-write":
                self.writes += 1
            data = self.receipt()
            return httpx.Response(200, json=[data] if path == "/api/orders" else data)
        if path.endswith("/scan"):
            return httpx.Response(200, json=dict(product_id=self.product,scan_id="scan",sellers_processed=3,
                sellers_skipped=0,findings=3,llm_mode=self.mode.upper(),stop_reason=None))
        if path.endswith("/marketplace"):
            expert = request.headers["X-Demo-Role"] == "REVIEWER"
            fields = [dict(field_key="volume", independent_clusters=3 if self.fault == "copies" else 2,
                values=[dict(value={"ml":137},display="137 ml",independent_clusters=2)],majority={"ml":137})]
            if self.fault == "empty-fields":
                fields = []
            elif self.fault == "empty-values":
                fields[0]["values"] = []
            elif self.fault == "duplicate-field":
                fields += deepcopy(fields)
            elif self.fault == "duplicate-value":
                fields[0]["values"] += deepcopy(fields[0]["values"])
            elif self.fault == "empty-unobserved":
                fields.append(dict(field_key="skin_type", independent_clusters=0, values=[], majority=None))
            data = dict(audience="EXPERT" if expert else "BUYER",product_id=self.product,scan_id="scan",fields=fields)
            if expert or self.fault == "buyer-leak":
                data["findings"] = [dict(seller_source_id=f"shop-{i}",shop=f"Seller {i}",field_key="volume",
                    value={"ml":137},display="137 ml",cluster="copy" if i < 2 else "independent",outlier=False,
                    citation=dict(passage_id=f"passage-{i}",source_kind="LISTING",source_version=1,locator="size",excerpt="137 ml"),
                    dataset_origin="SYNTHETIC") for i in range(3)]
            return httpx.Response(200,json=data)
        if path.endswith("/web-search"):
            buyer = request.headers["X-Demo-Role"] == "BUYER"
            if buyer and self.fault != "buyer-web":
                return httpx.Response(403,json={})
            if self.fault == "web-write":
                self.writes += 1
            return httpx.Response(200,json=dict(case_id=self.case,queries=[],snapshots=[]))
        raise AssertionError((method,path))


@pytest.mark.parametrize("mode", ["fallback", "replay"])
@pytest.mark.parametrize("fault", [None,"hash","rewrite","revision","collateral","omit","wrong-now",
                                  "duplicate","read-write","stub","no-job","partial","mode","unlinked",
                                  "lying-hash","stored-rewrite","wrong-product"])
def test_receipt_checker_rejects_bad_freeze_diff_and_lifecycle(mode: str, fault: str | None) -> None:
    story = Story(mode,fault)
    with httpx.Client(transport=httpx.MockTransport(story.handle),base_url="http://test") as client:
        if fault is None:
            check_receipt(client,story.count,story.product,story.case,mode,story.stored)
            assert story.events == ["01-bootstrap-demo","05-revoke-notification"]
        else:
            with pytest.raises((CheckFailure,ValidationError)):
                check_receipt(client,story.count,story.product,story.case,mode,story.stored)


@pytest.mark.parametrize("product", ["other-137", "variant-211"])
@pytest.mark.parametrize("fault", [None,"copies","buyer-leak","empty-fields","empty-values","duplicate-field","duplicate-value","wrong-product"])
def test_marketplace_checker_uses_clusters_and_closed_buyer_projection(product: str, fault: str | None) -> None:
    story = Story("fallback",fault,product)
    with httpx.Client(transport=httpx.MockTransport(story.handle),base_url="http://test") as client:
        if fault is None:
            check_marketplace(client,story.count,product,story.case,"unrelated-event","fallback")
        else:
            with pytest.raises((CheckFailure,ValidationError)):
                check_marketplace(client,story.count,product,story.case,"unrelated-event","fallback")


@pytest.mark.parametrize("fault", [None,"buyer-web","web-write"])
def test_web_audit_read_checks_role_and_no_work(fault: str | None) -> None:
    story = Story("fallback",fault)
    with httpx.Client(transport=httpx.MockTransport(story.handle),base_url="http://test") as client:
        if fault is None:
            check_web_audit(client,story.count,story.case,"fallback")
        else:
            with pytest.raises(CheckFailure):
                check_web_audit(client,story.count,story.case,"fallback")


def test_marketplace_allows_explicit_unavailable_field_without_invented_evidence() -> None:
    story = Story("fallback", "empty-unobserved")
    with httpx.Client(transport=httpx.MockTransport(story.handle), base_url="http://test") as client:
        check_marketplace(client, story.count, story.product, story.case, "another-bootstrap", "fallback")
    assert story.writes == 0


@pytest.mark.parametrize("fault", [None, "invented-count", "invented-majority", "read-write"])
@pytest.mark.parametrize("product", ["abstained-159", "unrelated-233"])
def test_marketplace_conservative_abstention_preserves_consistency(product: str, fault: str | None) -> None:
    story = Story("fallback", product=product)

    def respond(request: httpx.Request) -> httpx.Response:
        response = story.handle(request)
        if request.url.path.endswith("/scan"):
            data = response.json()
            data["findings"] = 1 if fault == "invented-count" else 0
            return httpx.Response(200, json=data)
        if request.url.path.endswith("/marketplace"):
            data = response.json()
            data["fields"] = [dict(field_key="volume", independent_clusters=0, values=[],
                                   majority={"ml":159} if fault == "invented-majority" else None)]
            if data["audience"] == "EXPERT":
                data["findings"] = []
            if fault == "read-write":
                story.writes += 1
            return httpx.Response(200, json=data)
        return response

    with httpx.Client(transport=httpx.MockTransport(respond), base_url="http://test") as client:
        if fault is None:
            check_marketplace(client, story.count, product, story.case, "arbitrary-bootstrap", "fallback")
            assert story.writes == 0
        else:
            with pytest.raises(CheckFailure):
                check_marketplace(client, story.count, product, story.case, "arbitrary-bootstrap", "fallback")
