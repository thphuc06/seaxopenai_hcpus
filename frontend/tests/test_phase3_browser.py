"""Phase-three preview interactions at the demo viewport, without a server."""
from playwright.sync_api import Page, expect
from test_phase1_browser import ARTIFACTS, BASE, PRODUCTS, open_operator, page


def test_why_role_projection_and_keyboard_close(page: Page) -> None:
    page.goto(f"{BASE}/buyer/{PRODUCTS[0]['id']}")
    button = page.get_by_test_id("why-open-skin_type")
    button.click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible()
    expect(dialog.locator(".explanation-view > p")).to_have_count(3)
    expect(dialog.get_by_role("heading", name="Decision trail")).to_have_count(0)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(ARTIFACTS / "why-buyer-1280x720.png"))
    page.keyboard.press("Escape")
    expect(button).to_be_focused()
    page.get_by_label("Demo role").select_option("REVIEWER")
    button.click()
    expect(dialog.get_by_role("heading", name="Decision trail")).to_be_visible()
    expect(dialog.get_by_text("Stored citations", exact=True)).to_be_visible()
    page.screenshot(path=str(ARTIFACTS / "why-expert-1280x720.png"))


def test_agent_preview_anchor_effect_and_budgets(page: Page) -> None:
    open_operator(page)
    page.get_by_test_id("event-btn-09-catalogue-published").click()
    panel = page.get_by_test_id("agent-panel")
    expect(panel.get_by_text("verified by code (anchor: preview-anchor)", exact=True)).to_be_visible()
    expect(panel.get_by_text("No change recorded.", exact=True)).to_be_visible()
    expect(panel.get_by_test_id("budget-meter-model_calls")).to_contain_text("0 / 3")
    expect(page.locator(".waterfall .nested-span")).to_have_count(1)
    panel.scroll_into_view_if_needed()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(ARTIFACTS / "agent-1280x720.png"))


def test_reviewer_search_graph_and_chain_preview(page: Page) -> None:
    page.goto(f"{BASE}/reviewer")
    page.get_by_label("Demo role").select_option("REVIEWER")
    page.get_by_test_id("review-task-volume").click()
    page.get_by_role("button", name="Explore evidence and dependencies").click()
    explorer = page.locator(".case-explorer")
    expect(explorer.get_by_text("Chain valid", exact=False)).to_be_visible()
    expect(explorer.locator(".dependency-edge").first).to_be_visible()
    explorer.get_by_label("Search stored passages").fill("ml")
    explorer.get_by_role("button", name="Search", exact=True).click()
    expect(explorer.get_by_text("ranking only — no answer generated", exact=True)).to_be_visible()
    expect(explorer.locator(".search-hit").first).to_be_visible()
    expect(explorer.locator("mark").first).to_have_text("ml")
    explorer.get_by_text("Ranking stages", exact=True).click()
    expect(explorer.get_by_role("heading", name="bm25", exact=True)).to_be_visible()
    explorer.scroll_into_view_if_needed()
    page.screenshot(path=str(ARTIFACTS / "case-explorer-1280x720.png"))
