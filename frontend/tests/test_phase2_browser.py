"""S2 interactions through the HTTP seam, fully offline and without servers."""
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
import json

import pytest
from playwright.sync_api import Page, Route, expect

from test_phase1_api_browser import ApiScenario, BASE, api_page

ARTIFACTS = Path(__file__).resolve().parents[1] / "node_modules/.cache/p3-phase2-screenshots"


@dataclass
class ReviewScenario:
    base: ApiScenario
    revision: int = 7
    review_status: int = 200
    review_code: str = "NO_CITATION"
    submissions: list[dict] = field(default_factory=list)
    reviews: list[dict] = field(default_factory=list)
    hold_review: bool = False
    held: list[Route] = field(default_factory=list)
    pending_history: bool = False
    history_routes: list[Route] = field(default_factory=list)
    task_key: str = "volume"
    closed: bool = False
    shared_passage: bool = False
    product_metadata: dict | None = None
    contract_upload: bool = False
    evidence_status: int | None = None
    upload_outcome: str = "ADMITTED"
    extra_task: bool = False
    malformed_upload: bool = False

    def task(self) -> dict:
        evidence = self.base.evidence()
        listing = deepcopy(evidence["citations"][0])
        listing.update(passage_id="unseen-listing", source_kind="LISTING", source_label="Seller listing", text="Seller states 120 ml.", excerpt="120 ml", locator="specification")
        if self.shared_passage:
            listing = {**evidence["citations"][0], "excerpt": "different"}
        evidence["citations"].append(listing)
        return {
            "id": "unseen-task", "case_id": "unseen-case", "product_id": self.base.passport["product_id"], "case_revision": self.revision,
            "result": {"id": f"unseen-result-{self.revision}", "field_key": self.task_key, "case_revision": self.revision, "verdict": "CONFLICTING", "conflict_locus": "LISTING_VS_SOURCE", "freshness": "CURRENT", "scope_match": "MATCH", "review_state": "NEEDS_REVIEW", "evidence_level": "PRODUCT_VERSION", "seller_attributable": False, "public_text": "The volume statements differ. Under review.", "citations": [{key: value for key, value in item.items() if key in {"passage_id", "source_kind", "source_version", "locator", "excerpt"}} for item in evidence["citations"]], "depends_on": [], "notes": [], "explain": [], "gap": None, "needs_scope_resolution": False, "created_at": "2026-10-31T03:30:00Z", "reason": "Source changed"},
            "evidence": evidence,
        }

    def history(self) -> dict:
        # Project the original scenario into P1's newly published S2 DTOs.
        original = self.task()["result"]
        result = {key: original[key] for key in ("id", "field_key", "case_revision", "verdict", "conflict_locus", "freshness", "review_state", "public_text", "citations", "created_at")}
        result.update(case_id="unseen-case", label="Conflicting", result_version=self.revision, checked_at=original["created_at"], superseded_by=None)
        results = [result]
        if self.extra_task:
            results.append({**result, "id": f"unseen-skin-result-{self.revision}", "field_key": "skin_type"})
        return {"case_id": "unseen-case", "case_revision": self.revision, "results": results, "reviews": self.reviews, "events": [], "requests": []}

    def respond(self, route: Route, path: str) -> None:
        if path.startswith("/api/products/") and path.endswith("/evidence") and self.evidence_status is not None:
            route.fulfill(status=self.evidence_status, json={"detail": "Optional evidence unavailable"})
        elif path == "/api/products" and self.product_metadata is not None:
            route.fulfill(json=[{"id": self.base.passport["product_id"], "name": "Unseen lotion", "brand": "Other listing", "variant": "120 ml", "market": "VN", "dataset_origin": "SYNTHETIC", "presentation": {"image": "", "image_alt": "", "price": 0, "currency": "VND", "shop": "Other shop", "official_store": False, "category": "", "passport_metadata": self.product_metadata}}])
        elif path == "/api/review/queue":
            self.base.requests.append((route.request.method, path, route.request.headers.get("x-demo-role", "")))
            task = self.task()
            item = {"id": task["id"], "case_id": task["case_id"], "field_key": task["result"]["field_key"], "result_id": task["result"]["id"], "case_revision": task["case_revision"], "reason_code": "SOURCE_CHANGE", "verdict": task["result"]["verdict"]}
            items = [item]
            if self.extra_task:
                items.append({**item, "id": "unseen-skin-task", "field_key": "skin_type", "result_id": f"unseen-skin-result-{self.revision}"})
            route.fulfill(json=[] if self.closed else items)
        elif path == "/api/cases/unseen-case/history":
            if self.pending_history:
                self.history_routes.append(route)
            else:
                route.fulfill(json=self.history())
        elif path == "/api/cases/unseen-case/reviews":
            self.submissions.append(route.request.post_data_json)
            if self.hold_review:
                self.held.append(route)
            elif self.review_status != 200:
                route.fulfill(status=self.review_status, json={"detail": {"code": self.review_code, "current_revision": self.revision + 1}})
            else:
                review = {"id": "durable-review", **self.submissions[-1], "case_id": "unseen-case", "reviewer_id": "unseen-reviewer", "override": self.submissions[-1].get("override"), "created_at": "2026-10-31T03:40:00Z", "review_state": "REVIEWED"}
                self.reviews.append(review)
                self.closed = True
                route.fulfill(json=review)
        elif path == "/api/cases/unseen-case/evidence":
            self.submissions.append(route.request.post_data_json)
            if self.malformed_upload:
                route.fulfill(json={"status": "ADMITTED"})
            elif self.contract_upload:
                route.fulfill(json={"event_id": "unseen-upload", "outcome": self.upload_outcome, "reason": "Evidence received" if self.upload_outcome == "ADMITTED" else f"Upload outcome: {self.upload_outcome}", "job_id": "unseen-upload-job" if self.upload_outcome == "ADMITTED" else None, "stale_fields": ["volume"] if self.upload_outcome == "ADMITTED" else []})
            else:
                route.fulfill(json={"event_id": "unseen-upload", "outcome": "ADMITTED", "reason": "Evidence received", "job_id": "unseen-upload-job", "stale_fields": ["volume"]})
        else:
            ApiScenario.respond(self.base, route, path)


@pytest.fixture
def review_page(api_page: tuple[Page, ApiScenario]) -> tuple[Page, ReviewScenario]:
    page, base = api_page
    scenario = ReviewScenario(base)
    base.respond = scenario.respond
    return page, scenario


def open_task(page: Page, scenario: ReviewScenario) -> None:
    page.goto(f"{BASE}/reviewer")
    page.get_by_label("Demo role").select_option("REVIEWER")
    page.get_by_test_id(f"review-task-{scenario.task_key}").click()
    expect(page.get_by_role("heading", name="Record a decision")).to_be_visible()


def test_approve_pins_revision_and_asserts_durable_decision_list(review_page: tuple[Page, ReviewScenario]) -> None:
    page, state = review_page
    open_task(page, state)
    expect(page.get_by_text("Seller text", exact=True)).to_be_visible()
    expect(page.get_by_test_id("review-approve")).to_be_disabled()
    page.get_by_label("Reason", exact=True).fill("Compared both stored passages")
    page.get_by_test_id("review-approve").click()
    expect(page.get_by_test_id("review-decision-durable-review")).to_contain_text("APPROVE")
    expect(page.get_by_test_id("review-decision-durable-review")).to_contain_text("Compared both stored passages")
    assert state.submissions == [{"result_id": "unseen-result-7", "case_revision": 7, "decision": "APPROVE", "reason": "Compared both stored passages"}]
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(ARTIFACTS / "reviewer-1280x720.png"), full_page=True)


def test_409_requires_reload_and_never_rebinds_the_open_form_silently(review_page: tuple[Page, ReviewScenario]) -> None:
    page, state = review_page
    open_task(page, state)
    state.review_status = 409
    page.get_by_label("Reason", exact=True).fill("Review of the opened revision")
    page.get_by_test_id("review-approve").click()
    expect(page.get_by_role("alert")).to_contain_text("revision 7 → 8")
    expect(page.get_by_test_id("review-approve")).to_be_disabled()
    state.revision = 8
    page.get_by_role("button", name="Reload case", exact=True).click()
    expect(page.get_by_label("Reason", exact=True)).to_have_value("")
    expect(page.get_by_test_id("review-approve")).to_be_disabled()
    state.review_status = 200
    page.get_by_label("Reason", exact=True).fill("Reviewed the new revision")
    page.get_by_test_id("review-approve").click()
    expect(page.get_by_test_id("review-decision-durable-review")).to_contain_text("Revision 8")
    assert [item["case_revision"] for item in state.submissions] == [7, 8]


@pytest.mark.parametrize("code", ["NO_CITATION", "FORBIDDEN_WORDING"])
def test_override_422_keeps_reason_and_allows_correction(review_page: tuple[Page, ReviewScenario], code: str) -> None:
    page, state = review_page
    open_task(page, state)
    page.get_by_label("Decision", exact=True).select_option("OVERRIDE")
    page.get_by_label("Reason", exact=True).fill("Explain the replacement finding")
    page.get_by_label("Public explanation", exact=True).fill("120 ml — information differs across the sources checked.")
    for checkbox in page.get_by_role("checkbox").all():
        checkbox.uncheck()
    state.review_status = 422
    state.review_code = code
    page.get_by_test_id("review-override").click()
    expect(page.get_by_text(code, exact=True)).to_be_visible()
    expect(page.get_by_label("Reason", exact=True)).to_have_value("Explain the replacement finding")
    assert state.submissions[-1]["override"]["citations"] == []
    state.review_status = 200
    page.get_by_role("checkbox").first.check()
    page.get_by_test_id("review-override").click()
    expect(page.get_by_test_id("review-decision-durable-review")).to_contain_text("OVERRIDE")
    assert len(state.submissions[-1]["override"]["citations"]) == 1
    assert "text" not in state.submissions[-1]["override"]["citations"][0]


def test_pending_review_prevents_duplicate_submit_and_role_change_unmounts_private_case(review_page: tuple[Page, ReviewScenario]) -> None:
    page, state = review_page
    open_task(page, state)
    state.hold_review = True
    page.get_by_label("Reason", exact=True).fill("Check the stored evidence")
    page.get_by_test_id("review-approve").dblclick()
    expect(page.get_by_test_id("review-approve")).to_be_disabled()
    assert len(state.submissions) == 1
    page.get_by_label("Demo role").select_option("BUYER")
    expect(page.get_by_role("article", name="Selected review case")).to_have_count(0)
    state.held[0].fulfill(json={"id": "late-review"})
    expect(page.get_by_text("Seller text", exact=True)).to_have_count(0)


def test_mobile_claim_task_and_reject_decision(review_page: tuple[Page, ReviewScenario]) -> None:
    page, state = review_page
    state.task_key = "claim:free_from:unseen"
    page.set_viewport_size({"width": 390, "height": 844})
    open_task(page, state)
    expect(page.get_by_text("Claim finding · Revision 7", exact=True)).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.get_by_label("Decision", exact=True).select_option("REJECT")
    page.get_by_label("Reason", exact=True).fill("Request another review of the passages")
    page.get_by_test_id("review-reject").click()
    expect(page.get_by_test_id("review-decision-durable-review")).to_contain_text("REJECT")
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(ARTIFACTS / "reviewer-mobile.png"), full_page=True)


def test_stale_ripple_only_on_change_and_claim_count_stays_on_ingredient_row(review_page: tuple[Page, ReviewScenario]) -> None:
    page, state = review_page
    page.clock.install()
    page.goto(f"{BASE}/buyer/{state.base.passport['product_id']}")
    expect(page.get_by_test_id("field-label-volume")).to_have_text("Consistent")
    expect(page.locator(".field-ripple")).to_have_count(0)
    state.base.passport["fields"][0]["freshness"] = "STALE"
    state.base.passport["fields"][2]["claims_under_review"] = 3
    page.clock.run_for(2500)
    expect(page.get_by_test_id("field-label-volume")).to_have_text("Stale")
    expect(page.get_by_test_id("field-row-volume").locator(".ripple-stale")).to_have_count(1)
    expect(page.get_by_test_id("field-row-key_ingredients")).to_contain_text("3 claims under review")
    state.base.passport["fields"][0]["freshness"] = "CURRENT"
    state.base.passport["fields"][0]["verdict"] = "INSUFFICIENT"
    page.clock.run_for(2500)
    expect(page.get_by_test_id("field-label-volume")).to_have_text("Not verified")
    expect(page.get_by_test_id("field-row-volume").locator(".ripple-change")).to_have_count(1)
    assert all(method == "GET" for method, _, _ in state.base.requests)


def test_scenario_next_uses_catalog_caption_and_retries_same_step_after_error(review_page: tuple[Page, ReviewScenario]) -> None:
    page, state = review_page
    page.goto(BASE)
    page.get_by_label("Demo role").select_option("OPERATOR")
    stepper = page.get_by_role("region", name="Scenario stepper")
    expect(stepper).to_contain_text("A preview of source change")
    page.get_by_test_id("scenario-next").click()
    expect(page.get_by_role("alert")).to_contain_text("501")
    expect(stepper).to_contain_text("Change an unrelated source")
    expect(page.get_by_test_id("scenario-next")).to_be_enabled()
    expect(page.get_by_role("region", name="Live buyer passport").get_by_test_id("field-row-volume")).to_be_visible()
    state.base.hold_event = True
    with page.expect_request("**/internal/demo/fire/unseen-change"):
        page.get_by_test_id("scenario-next").click()
    expect(page.get_by_test_id("scenario-next")).to_be_disabled()
    state.base.pending[0].fulfill(json={"event_id": "other-event", "outcome": "ADMITTED", "reason": "Source change queued", "job_id": "other-job", "stale_fields": ["volume"]})
    expect(stepper.get_by_role("heading", name="Scenario complete", exact=True)).to_be_visible()
    expect(page.get_by_test_id("scenario-next")).to_be_disabled()


def test_seller_json_upload_rejects_non_object_and_submits_exact_case_payload(review_page: tuple[Page, ReviewScenario]) -> None:
    page, state = review_page
    page.goto(f"{BASE}/buyer/{state.base.passport['product_id']}")
    expect(page.get_by_role("button", name="Submit evidence", exact=True)).to_have_count(0)
    page.get_by_label("Demo role").select_option("SELLER")
    page.get_by_label("Case reference", exact=True).fill("unseen-case")
    page.get_by_label("Evidence JSON", exact=True).fill("[]")
    page.get_by_role("button", name="Submit evidence", exact=True).click()
    expect(page.get_by_role("alert")).to_contain_text("JSON object")
    assert state.submissions == []
    payload = {"kind": "SELLER_UPLOAD", "passages": [{"text": "120 ml", "locator": "label/front"}]}
    page.get_by_label("Evidence JSON", exact=True).fill(json.dumps(payload))
    page.get_by_role("button", name="Submit evidence", exact=True).click()
    expect(page.get_by_text("Evidence submitted.", exact=False)).to_be_visible()
    assert state.submissions == [payload]


def test_optional_evidence_503_keeps_queue_and_stored_excerpts(review_page: tuple[Page, ReviewScenario]) -> None:
    page, state = review_page
    state.evidence_status = 503
    page.goto(f"{BASE}/reviewer")
    page.get_by_label("Demo role").select_option("REVIEWER")
    expect(page.get_by_test_id("review-task-volume")).to_be_visible()
    page.get_by_test_id("review-task-volume").click()
    case = page.get_by_role("article", name="Selected review case")
    expect(case.get_by_role("alert")).to_contain_text("503")
    expect(case.locator("blockquote")).to_have_text(["stored passage", "120 ml"])
    expect(page.get_by_label("Reason", exact=True)).to_be_enabled()


def test_pending_decision_survives_queue_and_workspace_remount(review_page: tuple[Page, ReviewScenario]) -> None:
    page, state = review_page
    state.extra_task = True
    open_task(page, state)
    state.hold_review = True
    page.get_by_label("Reason", exact=True).fill("Pending decision on the opened result")
    page.get_by_test_id("review-approve").click()
    expect(page.get_by_test_id("review-task-volume")).to_be_disabled()
    expect(page.get_by_test_id("review-task-skin_type")).to_be_disabled()
    page.get_by_role("link", name="Observe", exact=True).click()
    page.get_by_role("link", name="Reviewer", exact=True).click()
    page.get_by_test_id("review-task-volume").click()
    page.get_by_label("Reason", exact=True).fill("Attempt after reopening the workspace")
    page.get_by_test_id("review-approve").click()
    expect(page.get_by_role("article", name="Selected review case").get_by_role("alert")).to_contain_text("already being submitted")
    assert len(state.submissions) == 1
    state.held[0].fulfill(json={"id": "one-review", "case_id": "unseen-case", "result_id": "unseen-result-7", "case_revision": 7, "reviewer_id": "unseen-reviewer", "decision": "APPROVE", "reason": state.submissions[0]["reason"], "override": None, "created_at": "2026-10-31T03:40:00Z", "review_state": "REVIEWED"})


@pytest.mark.parametrize("outcome", ["ADMITTED", "REJECTED", "NOOP", "DUPLICATE"])
def test_upload_displays_admission_outcome_without_false_processing(review_page: tuple[Page, ReviewScenario], outcome: str) -> None:
    page, state = review_page
    state.contract_upload = True
    state.upload_outcome = outcome
    page.goto(f"{BASE}/buyer/{state.base.passport['product_id']}")
    page.get_by_label("Demo role").select_option("SELLER")
    page.get_by_label("Case reference", exact=True).fill("unseen-case")
    page.get_by_label("Evidence JSON", exact=True).fill(json.dumps({"idempotency_key": "upload-outcome-key", "field_keys": ["volume"], "content": {"kind": "TEXT", "text": "Volume 73 ml."}}))
    page.get_by_role("button", name="Submit evidence", exact=True).click()
    section = page.locator(".seller-evidence")
    expect(section.get_by_text(outcome, exact=True)).to_be_visible()
    expect(section.get_by_text("Evidence received" if outcome == "ADMITTED" else f"Upload outcome: {outcome}", exact=True)).to_be_visible()
    if outcome == "ADMITTED":
        expect(section.get_by_text("Evidence submitted.", exact=False)).to_be_visible()
    else:
        expect(section.get_by_text("Evidence submitted.", exact=False)).to_have_count(0)
        expect(section.get_by_text("Processing was queued.", exact=False)).to_have_count(0)


def test_upload_missing_admission_outcome_reports_error_without_success(review_page: tuple[Page, ReviewScenario]) -> None:
    page, state = review_page
    state.malformed_upload = True
    page.goto(f"{BASE}/buyer/{state.base.passport['product_id']}")
    page.get_by_label("Demo role").select_option("SELLER")
    page.get_by_label("Case reference", exact=True).fill("unseen-case")
    page.get_by_label("Evidence JSON", exact=True).fill(json.dumps({"idempotency_key": "malformed-response-key", "field_keys": ["volume"], "content": {"kind": "TEXT", "text": "Volume 73 ml."}}))
    page.get_by_role("button", name="Submit evidence", exact=True).click()
    section = page.locator(".seller-evidence")
    expect(section.get_by_role("alert")).to_be_visible()
    expect(section.get_by_text("Evidence submitted.", exact=False)).to_have_count(0)


def test_override_selects_distinct_excerpts_from_the_same_stored_passage(review_page: tuple[Page, ReviewScenario]) -> None:
    page, state = review_page
    state.shared_passage = True
    open_task(page, state)
    page.get_by_label("Decision", exact=True).select_option("OVERRIDE")
    page.get_by_label("Reason", exact=True).fill("Keep only the second cited excerpt")
    checkboxes = page.get_by_role("checkbox")
    expect(checkboxes).to_have_count(2)
    checkboxes.nth(0).uncheck()
    expect(checkboxes.nth(1)).to_be_checked()
    page.get_by_test_id("review-override").click()
    expect(page.get_by_test_id("review-decision-durable-review")).to_contain_text("OVERRIDE")
    assert state.submissions[-1]["override"]["citations"] == [state.task()["result"]["citations"][1]]


@pytest.mark.parametrize("mode", ["FALLBACK", "REPLAY"])
def test_operator_adjacent_passport_preserves_mode_and_hidden_count(review_page: tuple[Page, ReviewScenario], mode: str) -> None:
    page, state = review_page
    state.product_metadata = {"llm_mode": mode, "hidden_citations": {"volume": 2}}
    page.goto(BASE)
    page.get_by_label("Demo role").select_option("OPERATOR")
    passport = page.get_by_role("region", name="Live buyer passport")
    expect(passport.get_by_test_id("badge-mode")).to_have_text(mode)
    expect(passport.get_by_test_id("field-row-volume")).to_contain_text("2 private documents (reviewers only)")


@pytest.mark.parametrize("content", [{"kind": "TEXT", "text": "Contents 73 ml."}, {"kind": "IMAGE", "media_type": "image/png", "data_base64": "cG5nLXByZXZpZXctYnl0ZXM="}])
def test_seller_forwards_contract2_upload_and_admission_response(review_page: tuple[Page, ReviewScenario], content: dict) -> None:
    page, state = review_page
    state.contract_upload = True
    payload = {"idempotency_key": "unseen-upload-key", "field_keys": ["volume"], "content": content}
    page.goto(f"{BASE}/buyer/{state.base.passport['product_id']}")
    page.get_by_label("Demo role").select_option("SELLER")
    page.get_by_label("Case reference", exact=True).fill("unseen-case")
    page.get_by_label("Evidence JSON", exact=True).fill(json.dumps(payload))
    with page.expect_request("**/cases/unseen-case/evidence") as sent:
        page.get_by_role("button", name="Submit evidence", exact=True).click()
    expect(page.get_by_text("Evidence submitted.", exact=False)).to_be_visible()
    assert sent.value.headers["x-demo-role"] == "SELLER"
    assert state.submissions == [payload]
