"""Focused P3 component interactions; the worktree owns scripts/e2e.py."""
from playwright.sync_api import Page, expect
import re
from test_phase1_browser import ARTIFACTS, BASE, PRODUCTS, page


def test_purchase_then_source_change_preserves_receipt(page: Page) -> None:
    page.goto(f"{BASE}/buyer/{PRODUCTS[0]['id']}")
    page.get_by_test_id("buy-button").click()
    expect(page).to_have_url(re.compile(r"/orders/preview-order-"))
    receipt_path = page.url
    expect(page.get_by_test_id("receipt-diff")).to_contain_text("No changes since purchase")
    frozen = page.locator(".passport-card").text_content()
    page.get_by_role("link", name="Operator", exact=True).click()
    page.get_by_label("Demo role").select_option("OPERATOR")
    page.get_by_test_id("event-btn-05-revoke-notification").click()
    expect(page.get_by_test_id("web-audit")).to_be_visible()
    page.get_by_label("Demo role").select_option("BUYER")
    # SPA navigation keeps the explicit in-memory preview receipt.
    page.evaluate("path => { history.pushState({}, '', path); dispatchEvent(new PopStateEvent('popstate')); }", receipt_path)
    expect(page.get_by_test_id("receipt-diff")).to_contain_text("Changed since purchase")
    expect(page.locator(".passport-card")).to_have_text(frozen)
    expect(page.get_by_text("Receipt integrity references")).to_have_count(0)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(ARTIFACTS / "receipt-phase4-1280x720.png"))


def test_observe_role_gate_and_scorecard_empty_state(page: Page) -> None:
    page.goto(f"{BASE}/observe")
    expect(page.get_by_text("Expert access required.", exact=False)).to_be_visible()
    page.get_by_label("Demo role").select_option("REVIEWER")
    expect(page.get_by_role("heading", name="Model calls", exact=True)).to_be_visible()
    expect(page.get_by_text("Not computed yet", exact=True)).to_be_visible()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(ARTIFACTS / "observe-phase4-1280x720.png"))


def test_reviewer_web_audit_has_query_snapshot_and_decisions(page: Page) -> None:
    page.goto(f"{BASE}/reviewer")
    page.get_by_label("Demo role").select_option("REVIEWER")
    page.get_by_test_id("review-task-volume").click()
    page.get_by_role("button", name="Open web search audit").click()
    audit = page.get_by_test_id("web-audit")
    expect(audit.get_by_role("heading", name="Stored snapshots")).to_be_visible()
    expect(audit.get_by_text("identity verified", exact=True)).to_be_visible()
    expect(audit.get_by_text("skipped", exact=False)).to_be_visible()
    audit.scroll_into_view_if_needed()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(ARTIFACTS / "web-audit-phase4-1280x720.png"))
