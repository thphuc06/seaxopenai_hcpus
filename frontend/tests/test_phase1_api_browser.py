"""Browser tests for the real HTTP transport with deterministic offline responses."""
from collections.abc import Iterator
from copy import deepcopy
from dataclasses import dataclass, field
import json
import mimetypes
from pathlib import Path
from urllib.parse import unquote, urlparse

import pytest
from playwright.sync_api import Page, Route, expect, sync_playwright

FRONTEND = Path(__file__).resolve().parents[1]
BUILD = FRONTEND / "dist"
BASE = "http://p3-api.test"


@dataclass
class ApiScenario:
    passport: dict = field(default_factory=dict)
    requests: list[tuple[str, str, str]] = field(default_factory=list)
    evidence_error: bool = False
    hold_evidence: bool = False
    hold_event: bool = False
    pending: list[Route] = field(default_factory=list)

    def __post_init__(self) -> None:
        raw = json.loads((FRONTEND / "src/mock/passport.json").read_text(encoding="utf-8"))
        self.passport = {key: raw[key] for key in ("product_id", "dataset_origin", "last_checked_at", "run_status", "disclaimer")}
        self.passport["fields"] = [{key: value for key, value in item.items() if key not in {"hidden_citations", "claims_under_review"}} for item in raw["fields"]]
        self.passport["product_id"] = "unseen-browser-product"

    @staticmethod
    def evidence(text: str = "A different stored passage.", excerpt: str = "stored passage", visibility: str = "PUBLIC") -> dict:
        return {"citations": [{"passage_id": "unseen-passage", "source_kind": "BRAND_PAGE", "source_version": 4, "locator": "section#3", "excerpt": excerpt, "text": text, "source_label": "Different reference", "captured_at": "2026-10-31T02:00:00Z", "visibility": visibility}], "hidden_citations": 1}

    def respond(self, route: Route, path: str) -> None:
        role = route.request.headers.get("x-demo-role", "")
        self.requests.append((route.request.method, path, role))
        if path == "/api/products":
            route.fulfill(json=[{"id": self.passport["product_id"], "name": "Unseen lotion", "brand": "Other listing", "variant": "120 ml", "market": "VN", "dataset_origin": "SYNTHETIC", "presentation": None}])
        elif path.endswith("/passport"):
            route.fulfill(json=deepcopy(self.passport))
        elif path.endswith("/evidence"):
            if self.hold_evidence:
                self.pending.append(route)
            elif self.evidence_error:
                route.fulfill(status=501, json={"detail": "Endpoint implementation pending"})
            else:
                route.fulfill(json=self.evidence())
        elif path == "/api/internal/events/catalog":
            route.fulfill(json=[{"name": "unseen-change", "title": "Change an unrelated source", "type": "SOURCE_CHANGED", "product_id": self.passport["product_id"], "resource": {"kind": "SOURCE", "id": "source-unseen", "version": 2}, "expect": "A preview of source change"}])
        elif path == "/api/internal/metrics":
            route.fulfill(json={"events": {"ADMITTED": 0, "NOOP": 0, "DUPLICATE": 0, "REJECTED": 0}, "runs": 0, "jobs": 0, "model_calls": {"live": 2, "replayed": 3, "avoided": 4}, "passport_reads": 0})
        elif path == "/api/internal/runs":
            route.fulfill(json=[])
        elif path.startswith("/api/internal/demo/fire/"):
            if self.hold_event:
                self.pending.append(route)
            else:
                route.fulfill(status=501, json={"detail": "Endpoint implementation pending"})
        else:
            route.fulfill(status=404, json={"detail": "Missing test route"})


@pytest.fixture
def api_page() -> Iterator[tuple[Page, ApiScenario]]:
    assert (BUILD / "index.html").is_file(), "Build the API configuration into dist first"
    state = ApiScenario()
    errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 720})

        def intercept(route: Route) -> None:
            url = urlparse(route.request.url)
            assert url.netloc == "p3-api.test", "Test attempted an external network request"
            if url.path.startswith("/api/"):
                state.respond(route, url.path)
                return
            target = (BUILD / unquote(url.path).lstrip("/")).resolve()
            assert target.is_relative_to(BUILD.resolve())
            if not target.is_file():
                target = BUILD / "index.html"
            route.fulfill(body=target.read_bytes(), content_type=mimetypes.guess_type(target.name)[0] or "application/octet-stream")

        context.route("**/*", intercept)
        current = context.new_page()
        current.on("pageerror", lambda error: errors.append(str(error)))
        yield current, state
        context.close()
        browser.close()
    assert errors == []


def test_real_transport_handles_null_presentation_evidence_error_and_retry(api_page: tuple[Page, ApiScenario]) -> None:
    page, state = api_page
    state.evidence_error = True
    page.goto(f"{BASE}/buyer/{state.passport['product_id']}")
    expect(page.get_by_role("heading", name="Unseen lotion")).to_be_visible()
    expect(page.get_by_text("Product image unavailable")).to_be_visible()
    page.get_by_test_id("evidence-open-volume").click()
    alert = page.get_by_role("dialog").get_by_role("alert")
    expect(alert).to_contain_text("This information is not available yet. Please try again later.")
    expect(alert).not_to_contain_text("501")
    expect(alert).not_to_contain_text("/api/")
    expect(alert).not_to_contain_text("/fields/volume/evidence")
    expect(alert).not_to_contain_text("Endpoint implementation pending")
    state.evidence_error = False
    page.get_by_role("button", name="Retry evidence").click()
    expect(page.get_by_role("dialog").locator("mark")).to_have_text("stored passage")
    assert all(method == "GET" and role == "BUYER" for method, _, role in state.requests)


@pytest.mark.parametrize("role,field_key", [("OPERATOR", "volume"), ("REVIEWER", "skin_type")])
def test_expert_evidence_error_keeps_diagnostics_and_retry(api_page: tuple[Page, ApiScenario], role: str, field_key: str) -> None:
    page, state = api_page
    state.evidence_error = True
    page.goto(f"{BASE}/buyer/{state.passport['product_id']}")
    page.get_by_label("Demo role").select_option(role)
    page.get_by_test_id(f"evidence-open-{field_key}").click()
    alert = page.get_by_role("dialog").get_by_role("alert")
    expect(alert).to_contain_text("501")
    expect(alert).to_contain_text(f"/fields/{field_key}/evidence")
    state.evidence_error = False
    page.get_by_role("button", name="Retry evidence").click()
    expect(page.get_by_role("dialog").locator("mark")).to_have_text("stored passage")
    evidence_requests = [request for request in state.requests if request[1].endswith("/evidence")]
    assert len(evidence_requests) == 2
    assert all(method == "GET" and request_role == role for method, _, request_role in evidence_requests)
    assert all(method == "GET" for method, _, _ in state.requests)


def test_buyer_full_reload_only_issues_get_requests(api_page: tuple[Page, ApiScenario]) -> None:
    page, state = api_page
    page.goto(f"{BASE}/buyer/{state.passport['product_id']}")
    expect(page.get_by_test_id("field-row-volume")).to_be_visible()
    for _ in range(3):
        page.reload()
        expect(page.get_by_test_id("field-row-volume")).to_be_visible()
    assert sum(path.endswith("/passport") for _, path, _ in state.requests) >= 4
    assert all(method == "GET" for method, _, _ in state.requests)
    assert all(not path.startswith("/api/internal/") for _, path, _ in state.requests)


def test_field_switch_does_not_render_a_late_response_from_closed_drawer(api_page: tuple[Page, ApiScenario]) -> None:
    page, state = api_page
    state.hold_evidence = True
    page.goto(f"{BASE}/buyer/{state.passport['product_id']}")
    with page.expect_request("**/fields/volume/evidence"):
        page.get_by_test_id("evidence-open-volume").click()
    page.get_by_role("button", name="Close dialog").click()
    state.hold_evidence = False
    page.get_by_test_id("evidence-open-skin_type").click()
    expect(page.get_by_role("dialog").locator("mark")).to_have_text("stored passage")
    state.pending[0].fulfill(json=state.evidence("Old volume wording", "volume"))
    expect(page.get_by_role("dialog").get_by_role("heading", name="Skin type · Evidence")).to_be_visible()
    expect(page.get_by_role("dialog").locator("blockquote")).not_to_contain_text("Old volume wording")


def test_pending_event_cannot_be_submitted_twice_and_error_preserves_counters(api_page: tuple[Page, ApiScenario]) -> None:
    page, state = api_page
    state.hold_event = True
    page.goto(BASE)
    page.get_by_label("Demo role").select_option("OPERATOR")
    button = page.get_by_test_id("event-btn-unseen-change")
    with page.expect_request("**/internal/demo/fire/unseen-change"):
        button.dblclick()
    expect(button).to_be_disabled()
    assert len([request for request in state.requests if request[0] == "POST"]) == 1
    state.pending[0].fulfill(status=501, json={"detail": "Endpoint implementation pending"})
    expect(page.get_by_role("alert")).to_contain_text("501")
    expect(button).to_be_enabled()
    expect(page.get_by_test_id("model-calls-counter")).to_have_text("5")


def test_new_action_clears_prior_outcome_and_reset_does_not_inherit_event_error(api_page: tuple[Page, ApiScenario]) -> None:
    page, state = api_page
    state.hold_event = True
    page.goto(BASE)
    page.get_by_label("Demo role").select_option("OPERATOR")
    button = page.get_by_test_id("event-btn-unseen-change")
    with page.expect_request("**/internal/demo/fire/unseen-change"):
        button.click()
    state.pending[0].fulfill(json={"event_id": "unseen-success", "outcome": "ADMITTED", "reason": "The first request was admitted.", "job_id": "unseen-job", "stale_fields": ["skin_type"]})
    expect(page.locator(".event-toast strong")).to_have_text("ADMITTED")
    with page.expect_request("**/internal/demo/fire/unseen-change"):
        button.click()
    expect(button).to_be_disabled()
    expect(page.locator(".event-toast")).to_have_count(0)
    state.pending[1].fulfill(status=501, json={"detail": "Second request unavailable"})
    expect(page.get_by_role("alert")).to_contain_text("501")
    expect(page.locator(".event-toast")).to_have_count(0)
    expect(page.get_by_test_id("model-calls-counter")).to_have_text("5")
    page.get_by_role("button", name="Reset demo", exact=True).click()
    expect(page.get_by_role("dialog").get_by_role("alert")).to_have_count(0)
    expect(page.get_by_role("button", name="Confirm reset", exact=True)).to_be_enabled()


@pytest.mark.parametrize("status,label", [("RUNNING", "Updating"), ("FAILED", "Consistent")])
def test_transient_status_preserves_stale_precedence(api_page: tuple[Page, ApiScenario], status: str, label: str) -> None:
    page, state = api_page
    state.passport["run_status"] = status
    page.goto(f"{BASE}/buyer/{state.passport['product_id']}")
    expect(page.get_by_test_id("field-label-volume")).to_have_text(label)
    expect(page.get_by_test_id("field-label-responsible_company")).to_have_text("Stale")
    if status == "FAILED":
        expect(page.get_by_text("This says nothing about the product.")).to_be_visible()
