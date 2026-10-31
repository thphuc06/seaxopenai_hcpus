"""Offline interactions against the built mock bundle; no listening server."""
from collections.abc import Iterator
import json
import mimetypes
from pathlib import Path
from urllib.parse import unquote, urlparse

import pytest
from playwright.sync_api import Page, Route, expect, sync_playwright

FRONTEND = Path(__file__).resolve().parents[1]
BUILD = FRONTEND / "node_modules/.cache/p3-mock-build"
ARTIFACTS = FRONTEND / "node_modules/.cache/p3-phase1-screenshots"
PRODUCTS = json.loads((FRONTEND / "src/mock/products.json").read_text(encoding="utf-8"))
CATALOG = json.loads((FRONTEND / "src/mock/catalog.json").read_text(encoding="utf-8"))
BASE = "http://p3-preview.test"


@pytest.fixture
def page() -> Iterator[Page]:
    assert (BUILD / "index.html").is_file(), "Build with VITE_USE_MOCK=1 into node_modules/.cache/p3-mock-build first"
    errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 720})

        def local_files(route: Route) -> None:
            url = urlparse(route.request.url)
            if url.netloc != "p3-preview.test" or route.request.method != "GET":
                errors.append(f"Unexpected request: {route.request.method} {url.path}")
                route.abort()
                return
            relative = unquote(url.path).lstrip("/")
            target = (BUILD / relative).resolve()
            if not target.is_relative_to(BUILD.resolve()):
                route.abort()
                return
            if not target.is_file():
                target = BUILD / "index.html"
            content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            route.fulfill(body=target.read_bytes(), content_type=content_type)

        context.route("**/*", local_files)
        current = context.new_page()
        current.on("pageerror", lambda error: errors.append(str(error)))
        yield current
        context.close()
        browser.close()
    assert errors == []


def open_operator(page: Page) -> None:
    page.goto(BASE)
    page.get_by_label("Demo role").select_option("OPERATOR")
    expect(page.get_by_test_id(f"event-btn-{CATALOG[0]['name']}")).to_be_enabled()


def test_buyer_opens_highlighted_pair_and_restores_keyboard_focus(page: Page) -> None:
    page.goto(f"{BASE}/buyer/{PRODUCTS[0]['id']}")
    button = page.get_by_test_id("evidence-open-skin_type")
    expect(button).to_be_enabled()
    button.click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible()
    expect(dialog.locator("blockquote")).to_have_count(2)
    expect(dialog.locator("mark")).to_have_count(2)
    expect(dialog.get_by_role("heading", name="Brand page", exact=True)).to_have_count(1)
    expect(dialog.get_by_text("This is not attributed to the seller.", exact=False)).to_be_visible()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(ARTIFACTS / "evidence-1280x720.png"))
    page.keyboard.press("Escape")
    expect(dialog).to_have_count(0)
    expect(button).to_be_focused()
    page.get_by_test_id("evidence-open-notification_number").click()
    expect(page.get_by_role("dialog").get_by_text("No source passage is available for this field.")).to_be_visible()
    page.get_by_role("button", name="Close dialog").click()


def test_operator_outcomes_trace_and_cancelled_then_confirmed_reset(page: Page) -> None:
    open_operator(page)
    for entry, outcome in zip(CATALOG, ("ADMITTED", "NOOP", "DUPLICATE", "REJECTED"), strict=True):
        page.get_by_test_id(f"event-btn-{entry['name']}").click()
        expect(page.locator(".event-toast strong")).to_have_text(outcome)
    expect(page.get_by_test_id("model-calls-counter")).to_have_text("0")
    expect(page.get_by_test_id("run-status")).to_have_text("COMPLETED")
    expect(page.get_by_role("cell", name="publish", exact=True)).to_be_visible()
    expect(page.locator(".run-item")).to_have_count(1)
    page.get_by_role("button", name="Reset demo", exact=True).click()
    page.get_by_role("button", name="Cancel", exact=True).click()
    expect(page.locator(".run-item")).to_have_count(1)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(ARTIFACTS / "operator-1280x720.png"), full_page=True)
    page.get_by_role("button", name="Reset demo", exact=True).click()
    page.get_by_role("button", name="Confirm reset", exact=True).click()
    expect(page.get_by_role("dialog")).to_have_count(0)
    expect(page.get_by_text("Demo data reset.", exact=True)).to_be_visible()
    expect(page.locator(".run-item")).to_have_count(0)


def test_buyer_navigation_does_not_add_model_calls_or_jobs(page: Page) -> None:
    open_operator(page)
    page.get_by_test_id(f"event-btn-{CATALOG[0]['name']}").click()
    expect(page.get_by_test_id("run-status")).to_have_text("COMPLETED")
    before = page.get_by_test_id("model-calls-counter").inner_text()
    for _ in range(3):
        page.get_by_role("link", name="Buyer Passport", exact=True).click()
        expect(page.get_by_test_id("field-row-volume")).to_be_visible()
        page.get_by_role("link", name="Operator", exact=True).click()
        expect(page.get_by_test_id("model-calls-counter")).to_have_text(before)
        expect(page.locator(".run-item")).to_have_count(1)
    page.get_by_label("Demo role").select_option("BUYER")
    expect(page.get_by_test_id(f"event-btn-{CATALOG[0]['name']}")).to_have_count(0)


def test_evidence_drawer_fits_mobile_and_can_be_closed(page: Page) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{BASE}/buyer/{PRODUCTS[0]['id']}")
    page.get_by_test_id("evidence-open-skin_type").click()
    dialog = page.get_by_role("dialog")
    expect(dialog.locator("mark")).to_have_count(2)
    bounds = dialog.bounding_box()
    assert bounds is not None
    assert bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= 390
    assert bounds["y"] >= 0 and bounds["height"] <= 844
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(ARTIFACTS / "evidence-mobile.png"))
    page.get_by_role("button", name="Close dialog").click()
    expect(dialog).to_have_count(0)
