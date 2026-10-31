"""Offline script/UI handoff checks; no Local server or replay is exercised."""
from pathlib import Path
from datetime import datetime, timezone
import sys

import pytest
from playwright.sync_api import Page, Route, expect

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from e2e import Journey
from test_phase1_api_browser import ApiScenario, BASE, api_page
from test_phase2_browser import ReviewScenario, review_page


@pytest.mark.parametrize("field_key", ["volume", "key_ingredients"])
def test_operator_refreshes_stored_passport_after_event_before_next_poll(api_page: tuple[Page, ApiScenario], field_key: str) -> None:
    page, state = api_page
    page.clock.install(time=datetime(2026, 10, 31, 8, tzinfo=timezone.utc))
    page.clock.pause_at(datetime(2026, 10, 31, 9, tzinfo=timezone.utc))
    state.passport["run_status"] = "COMPLETED"
    for item in state.passport["fields"]:
        item["freshness"] = "CURRENT"

    def admit(route: Route) -> None:
        next(item for item in state.passport["fields"] if item["field_key"] == field_key)["freshness"] = "STALE"
        route.fulfill(json={"event_id":"unrelated-admission", "outcome":"ADMITTED", "reason":"Source changed.", "stale_fields":[field_key]})

    page.route("**/api/internal/demo/fire/unseen-change", admit)
    page.goto(BASE)
    page.get_by_label("Demo role").select_option("OPERATOR")
    label = page.get_by_test_id("field-label-" + field_key)
    expect(label).to_be_visible()
    expect(label).not_to_have_text("Stale")
    reads = sum(path.endswith("/passport") for _, path, _ in state.requests)
    page.get_by_test_id("event-btn-unseen-change").click()
    expect(label).to_have_text("Stale", timeout=1900)
    assert sum(path.endswith("/passport") for _, path, _ in state.requests) > reads


@pytest.mark.parametrize("product", ["another-product", "product with space"])
def test_script_control_room_retains_nondefault_product(api_page: tuple[Page, ApiScenario], product: str, tmp_path: Path) -> None:
    page, state = api_page
    state.passport["product_id"] = product
    page.route("**/api/products", lambda route: route.fulfill(json=[
        {"id": key, "name": key, "brand": "Example", "variant": "120 ml", "market": "VN", "dataset_origin": "SYNTHETIC", "presentation": None}
        for key in ("default-decoy", product)
    ]))
    journey = Journey(page, BASE, BASE + "/api", tmp_path)
    journey.operator_for(product)
    expect(page.get_by_test_id("operator-nav")).to_have_count(1)
    expect(page.get_by_label("Selected product")).to_have_value(product)
    expect(page.get_by_test_id("field-row-volume")).to_be_visible()
    assert all(method == "GET" for method, _, _ in state.requests)


def test_recorder_reason_selector_submits_durable_decision(review_page: tuple[Page, ReviewScenario]) -> None:
    page, state = review_page
    page.goto(BASE + "/reviewer")
    page.get_by_label("Demo role").select_option("REVIEWER")
    page.get_by_test_id("review-task-volume").click()
    reason = "Checked this unrelated stored revision."
    page.get_by_test_id("review-reason").fill(reason)
    page.get_by_test_id("review-approve").click()
    expect(page.get_by_test_id("review-decision-durable-review")).to_contain_text(reason)
    assert state.submissions[0]["reason"] == reason
