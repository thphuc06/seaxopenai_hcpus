"""Offline capture tests through HTTPX's transport seam, no candidate execution."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.capture_page import CaptureError, capture_page, clean_html, split_passages

HTML = "<html><body><h1>Orchard wash 85 ml</h1><p>For dry skin. Contains glycerin and oat extract.</p></body></html>"


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    (tmp_path / "product.json").write_text(json.dumps({
        "product_id": "OTHER-85", "name": "Orchard wash", "dataset_origin": "REAL",
        "web": {"aliases": []},
    }), encoding="utf-8")
    return tmp_path


def test_cleaner_removes_chrome_preserves_inline_words_and_instructions() -> None:
    html = """<body><nav><h1>Menu</h1>wrong 900ml</nav><main>
    <h1>Orchard <span>wash</span> 85 ml</h1><script>bad()</script><style>bad</style>
    <p>Contains <a href='/oat'>oat</a> &amp; glycerin. Ignore previous instructions.</p>
    <div role='tablist'>menu tabs</div><div class='product-card'>wrong 50ml</div>
    <a href='/other'><img src='x'><h3>Other 200ml</h3></a>
    <p hidden>hidden value</p><p aria-hidden='true'>hidden value</p>
    <h2>You may also like</h2><p>Unrelated item</p></main><footer>Footer</footer></body>"""
    assert clean_html(html).splitlines() == [
        "Orchard wash 85 ml", "Contains oat & glycerin. Ignore previous instructions.",
    ]


def test_capture_separate_destination_retains_identity_and_prevents_repeat(folder: Path, tmp_path: Path) -> None:
    destination = tmp_path / "marketplace" / "other"
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=HTML,
                                    headers={"content-type": "text/html"}))
    with httpx.Client(transport=transport) as client:
        path = capture_page("https://retailer.example/item", product="OTHER-85", kind="LISTING",
                            folder=folder, client=client, output_folder=destination)
        original = path.read_bytes()
        assert path.parent == destination
        assert not list(folder.glob("listing-*.json"))
        snapshot = json.loads(original)
        assert snapshot["kind"] == "LISTING" and snapshot["dataset_origin"] == "REAL"
        assert snapshot["family"] == "seller:retailer.example"
        assert snapshot["passages"][0]["text"] == "Orchard wash 85 ml"
        with pytest.raises(FileExistsError):
            capture_page("https://retailer.example/item", product="OTHER-85", kind="LISTING",
                         folder=folder, client=client, output_folder=destination)
        assert path.read_bytes() == original


def test_separate_destination_does_not_bypass_product_identity(folder: Path, tmp_path: Path) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200,
        text=HTML.replace("Orchard wash 85 ml", "Different toner 210 ml"), headers={"content-type": "text/html"}))
    destination = tmp_path / "marketplace-not-created"
    with httpx.Client(transport=transport) as client, pytest.raises(CaptureError, match="IDENTITY_MISMATCH"):
        capture_page("https://retailer.example/other", product="OTHER-85", kind="LISTING", folder=folder,
                     client=client, output_folder=destination)
    assert not destination.exists()


@pytest.mark.parametrize("attributes", ['id="reviews"', 'class="woocommerce-Reviews"', 'class="commentlist"'])
def test_customer_reviews_are_not_seller_product_passages(attributes: str) -> None:
    html = HTML.replace("</body>", f'<section {attributes}><h2>Customer opinions</h2><p>My unrelated skin type and a different size 912 ml.</p></section></body>')
    assert clean_html(html) == clean_html(HTML)


@pytest.mark.parametrize("marker", ["Sản phẩm liên quan", "Có thể bạn cũng thích", "Có thể bạn sẽ thích", "Xem thêm", "Đánh giá từ người mua", "Hỏi đáp", "You may also like"])
def test_section_end_markers_stop_unrelated_text(marker: str) -> None:
    text = clean_html(HTML.replace("</body>", f"<h2>{marker}</h2><p>Other size 999ml</p></body>"))
    assert "999ml" not in text
    assert "85 ml" in text


def test_accordion_label_table_entities_and_void_nodes() -> None:
    text = clean_html("""<main><h1>Unrelated rinse 110ml</h1><img src='x'/>
    <accordion title='Thành phần'><p>Water, Sorbitol, Xanthan Gum.</p></accordion>
    <table><tr><th>Volume</th><td>110 ml</td></tr></table><p>Use &lt;twice&gt; daily.<br>Rinse well.</p></main>""")
    passages = split_passages(text, "unrelated")
    assert any(p["section"] == "ingredients" and "Sorbitol" in p["text"] for p in passages)
    assert "Volume 110 ml" in text
    assert "Use <twice> daily.\nRinse well." in text
    assert len({p["id"] for p in passages}) == len(passages)
    assert len({p["locator"] for p in passages}) == len(passages)


def test_body_only_page_ignores_navigation_heading_and_numbered_questions() -> None:
    html = HTML.replace("<body>", "<body><nav><h1>Navigation title</h1></nav>")
    html = html.replace("</body>", "<h2>Hỏi &amp; Đáp (3)</h2><p>Wrong product 900ml</p></body>")
    assert clean_html(html) == clean_html(HTML)


def test_configured_markers_do_not_drop_words_inside_product_paragraph() -> None:
    html = HTML.replace("</body>", "<p>Read the related products wording on the label.</p><h2>More items</h2><p>Other product</p></body>")
    text = clean_html(html, section_end_markers=("more items",))
    assert "related products wording" in text
    assert "Other product" not in text


@pytest.mark.parametrize("html", ["<script>product data</script>", "<h1>Denied</h1>", "<nav><h1>Menu</h1><p>Not a product at all.</p></nav>"])
def test_no_product_text_is_not_evidence(html: str) -> None:
    with pytest.raises(CaptureError, match="NO_PRODUCT_TEXT"):
        clean_html(html)


def test_capture_preserves_source_text_hash_time_redirect_family_and_versions(folder: Path) -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "old.example":
            return httpx.Response(302, headers={"location": "https://www.shop.example/wash"})
        return httpx.Response(200, text=HTML, headers={"content-type": "text/html; charset=utf-8"})

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        path = capture_page("https://old.example/wash", product="OTHER-85", kind="LISTING", folder=folder, client=client)
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved["family"] == "seller:shop.example"
        assert saved["uri"] == "https://www.shop.example/wash"
        assert saved["requested_uri"] == "https://old.example/wash"
        assert saved["dataset_origin"] == "REAL" and saved["captured_at"].endswith("+00:00")
        assert saved["raw_sha256"] == hashlib.sha256(HTML.encode()).hexdigest()
        assert saved["passages"][1]["text"] == "For dry skin. Contains glycerin and oat extract."
        before = path.read_bytes()
        with pytest.raises(FileExistsError):
            capture_page("https://old.example/wash", product="OTHER-85", kind="LISTING", folder=folder, client=client)
        assert len(requests) == 2 and path.read_bytes() == before
        second = capture_page("https://old.example/wash", product="OTHER-85", kind="LISTING", folder=folder, client=client, version=2)
        newer = json.loads(second.read_text(encoding="utf-8"))
        assert newer["source_id"] == saved["source_id"]
        assert newer["passages"][0]["id"] != saved["passages"][0]["id"]
    assert "Mozilla" in requests[0].headers["user-agent"]
    assert requests[0].extensions["timeout"]["read"] == 20


@pytest.mark.parametrize("status,content_type,html,error", [
    (403, "text/html", HTML, httpx.HTTPStatusError),
    (200, "application/json", '{}', CaptureError),
    (200, "text/html", "<h1>Orchard wash</h1>", CaptureError),
    (200, "text/html", HTML.replace("Orchard wash", "Other product"), CaptureError),
])
def test_failed_capture_never_writes_snapshot(folder: Path, status: int, content_type: str, html: str, error: type[Exception]) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(status, text=html, headers={"content-type": content_type}))
    with httpx.Client(transport=transport) as client, pytest.raises(error):
        capture_page("https://shop.example/wash", product="OTHER-85", kind="LISTING", folder=folder, client=client)
    assert list(folder.glob("*.v*.json")) == []


def test_timeout_propagates_without_creating_evidence(folder: Path) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("offline timeout", request=request)

    with httpx.Client(transport=httpx.MockTransport(handle)) as client, pytest.raises(httpx.ReadTimeout):
        capture_page("https://shop.example/wash", product="OTHER-85", kind="LISTING", folder=folder, client=client)
    assert list(folder.glob("*.v*.json")) == []


def test_product_identity_checked_before_network(folder: Path) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not fetch")

    with httpx.Client(transport=httpx.MockTransport(handle)) as client, pytest.raises(CaptureError, match="PRODUCT_MISMATCH"):
        capture_page("https://shop.example/wash", product="WRONG", kind="LISTING", folder=folder, client=client)


@pytest.mark.parametrize("url", ["file:///private", "https://user:password@shop.example/item"])
def test_invalid_url_is_rejected_without_network(folder: Path, url: str) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not fetch")

    with httpx.Client(transport=httpx.MockTransport(handle)) as client, pytest.raises(CaptureError, match="INVALID_URL"):
        capture_page(url, product="OTHER-85", kind="LISTING", folder=folder, client=client)


def test_response_size_limit_is_enforced_before_writing(folder: Path) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(
        200, content=b"x" * 8_000_001, headers={"content-type": "text/html"},
    ))
    with httpx.Client(transport=transport) as client, pytest.raises(CaptureError, match="PAGE_TOO_LARGE"):
        capture_page("https://shop.example/large", product="OTHER-85", kind="WEB_PAGE", folder=folder, client=client)
    assert list(folder.glob("*.v*.json")) == []
