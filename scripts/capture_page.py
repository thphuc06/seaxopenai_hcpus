"""Capture public product HTML as immutable REAL source snapshots; no model calls."""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from typing import Literal, TypedDict
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[1]
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
MAX_BYTES = 8_000_000
Kind = Literal["LISTING", "BRAND_PAGE", "WEB_PAGE"]
# DATASET-SPEC section 6. P2 can supply its data-owned list when it exists.
SECTION_END_MARKERS = (
    "sản phẩm liên quan", "có thể bạn cũng thích", "có thể bạn sẽ thích",
    "xem thêm", "đánh giá từ người mua", "hỏi đáp", "you may also like",
)
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
DROP = {"script", "style", "nav", "footer", "noscript", "svg", "form", "button", "template"}
BLOCK = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "div", "section", "article", "tr", "dt", "dd", "br"}
CHROME = re.compile(r"(?:^|[\s_-])(?:menu|breadcrumb|related|recommendations?|product-card|link-card|cookie|social|newsletter|reviews?|comments?|commentlist)(?:$|[\s_-])", re.I)


class CaptureError(ValueError):
    """No usable product page was captured; callers must report the reason."""


@dataclass
class Node:
    tag: str
    attrs: dict[str, str]
    children: list[Node | str] = field(default_factory=list)


class ProductHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("document", {})
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag, {key: value or "" for key, value in attrs})
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)


def _nodes(node: Node, tag: str) -> list[Node]:
    found = [node] if node.tag == tag else []
    for child in node.children:
        if isinstance(child, Node):
            found.extend(_nodes(child, tag))
    return found


def _discard(node: Node) -> bool:
    attrs = node.attrs
    return bool(node.tag in DROP or "hidden" in attrs or attrs.get("aria-hidden") == "true"
            or attrs.get("role") in {"navigation", "menu", "dialog", "tablist"}
            or CHROME.search(attrs.get("class", "") + " " + attrs.get("id", "")))


def _visible_nodes(node: Node, tag: str) -> list[Node]:
    if _discard(node):
        return []
    found = [node] if node.tag == tag else []
    for child in node.children:
        if isinstance(child, Node):
            found.extend(_visible_nodes(child, tag))
    return found


def _render(node: Node) -> str:
    attrs = node.attrs
    if _discard(node):
        return ""
    # Remove linked product cards, but preserve ordinary inline reference links.
    if node.tag == "a" and (_nodes(node, "img") or _nodes(node, "h2") or _nodes(node, "h3")):
        return ""
    text = "".join(child if isinstance(child, str) else _render(child) for child in node.children)
    # Custom accordion components expose their visible label as a title attribute.
    if node.tag == "accordion" and attrs.get("title"):
        text = "\n" + attrs["title"] + "\n" + text + "\n"
    if node.tag in {"td", "th"}:
        return text + " "
    return f"\n{text}\n" if node.tag in BLOCK else text


def clean_html(html: str, *, section_end_markers: tuple[str, ...] = SECTION_END_MARKERS) -> str:
    """Return product text with line boundaries, preserving source case/punctuation.

    Pure, importable helper for P2. It does not fetch, infer scope or decide verdicts.
    Require a visible h1 and body text; script-only shells are never REAL evidence.
    """
    parser = ProductHTML()
    parser.feed(html)
    parser.close()
    containers = _visible_nodes(parser.root, "main") or _visible_nodes(parser.root, "body") or [parser.root]
    container = next((node for node in containers if _visible_nodes(node, "h1")), containers[0])
    headings = _visible_nodes(container, "h1")
    if not headings:
        raise CaptureError("NO_PRODUCT_TEXT: no product h1")
    title = " ".join(_render(headings[0]).split())
    if not title:
        raise CaptureError("NO_PRODUCT_TEXT: empty product h1")
    lines = [" ".join(line.split()) for line in _render(container).splitlines() if line.strip()]
    try:
        start = lines.index(title)
    except ValueError as exc:
        raise CaptureError("NO_PRODUCT_TEXT: product heading was removed") from exc
    kept: list[str] = []
    for line in lines[start:]:
        marker = re.sub(r"\s*\(\d+\)\s*$", "", line.casefold()).rstrip(":")
        if marker in section_end_markers or marker in {"hỏi & đáp", "q&a", "questions and answers"}:
            break
        if not kept or line != kept[-1]:
            kept.append(line)
    if len(kept) < 2 or len(" ".join(kept[1:])) < 40:
        raise CaptureError("NO_PRODUCT_TEXT: no substantive text after title")
    return "\n".join(kept)


class Passage(TypedDict):
    id: str
    locator: str
    section: str
    text: str


def split_passages(text: str, source_id: str) -> list[Passage]:
    """Give retained text stable, ordered locators without rewriting its words."""
    passages: list[Passage] = []
    section = "description"
    counters: dict[str, int] = {}
    for index, line in enumerate(text.splitlines()):
        lower = line.casefold().rstrip(":")
        if index == 0:
            section = "title"
        elif lower in {"thành phần", "ingredients", "ingredient list", "bảng thành phần"}:
            section = "ingredients"
        elif lower in {"cách dùng", "cách sử dụng", "hướng dẫn sử dụng", "usage", "how to use", "đối tượng sử dụng"}:
            section = "usage"
        elif lower in {"thông tin sản phẩm", "thông tin sản xuất", "thông tin chi tiết", "thông số", "specifications", "chi tiết sản phẩm", "quy cách"}:
            section = "specs"
        elif lower in {"công dụng", "benefits", "highlights", "đặc điểm nổi bật"}:
            section = "highlights"
        elif lower in {"mô tả", "mô tả sản phẩm", "description"} or section == "title":
            section = "description"
        counters[section] = counters.get(section, 0) + 1
        number = counters[section]
        locator = "title" if section == "title" else f"{section}#{'p' if section == 'description' else ''}{number}"
        passages.append({"id": f"{source_id}-p{index + 1:03d}", "locator": locator, "section": section, "text": line})
    return passages


def fetch_page(url: str, *, client: httpx.Client) -> tuple[str, bytes, str]:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        raise CaptureError("INVALID_URL: public HTTP(S) URL required")
    with client.stream("GET", url, headers={"User-Agent": USER_AGENT}, timeout=20, follow_redirects=True) as response:
        response.raise_for_status()
        if "text/html" not in response.headers.get("content-type", "").lower():
            raise CaptureError("NOT_HTML: response content type")
        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > MAX_BYTES:
                raise CaptureError("PAGE_TOO_LARGE")
            chunks.append(chunk)
        body = b"".join(chunks)
        encoding = response.encoding or "utf-8"
        return str(response.url), body, body.decode(encoding, errors="strict")


def capture_page(url: str, *, product: str, kind: Kind, folder: Path,
                 client: httpx.Client, family: str | None = None, version: int = 1,
                 output_folder: Path | None = None) -> Path:
    """Capture one source. Product metadata must exist; existing versions are immutable."""
    metadata = json.loads((folder / "product.json").read_text(encoding="utf-8"))
    if metadata.get("product_id") != product or metadata.get("dataset_origin") != "REAL":
        raise CaptureError("PRODUCT_MISMATCH: expected matching REAL product.json")
    if version < 1:
        raise CaptureError("INVALID_VERSION")
    identity = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    source_id = f"{product}-{kind.lower()}-{identity}"
    path = (output_folder or folder) / f"{kind.lower()}-{identity}.v{version}.json"
    if path.exists():
        raise FileExistsError(f"Snapshot exists; use a new --version: {path}")
    final_url, raw, html = fetch_page(url, client=client)
    cleaned = clean_html(html)
    aliases = [str(metadata["name"]), *metadata.get("web", {}).get("aliases", [])]
    title = cleaned.splitlines()[0].casefold()
    if not any(alias.casefold() in title for alias in aliases if alias.strip()):
        raise CaptureError("IDENTITY_MISMATCH: product name/alias not present in h1")
    domain = (urlsplit(final_url).hostname or "").removeprefix("www.").lower()
    snapshot = {
        "source_id": source_id, "kind": kind, "product_id": product, "version": version,
        "uri": final_url, "requested_uri": url,
        "captured_at": datetime.now(timezone.utc).isoformat(), "dataset_origin": "REAL",
        "visibility": "PUBLIC", "family": family or f"{'brand' if kind == 'BRAND_PAGE' else 'seller'}:{domain}",
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "cleaned_sha256": hashlib.sha256(cleaned.encode("utf-8")).hexdigest(),
        "cleaner_version": "html-parser-v2", "passages": split_passages(cleaned, f"{source_id}-v{version}"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as output:
        output.write(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--product", required=True)
    parser.add_argument("--kind", required=True, choices=["LISTING", "BRAND_PAGE", "WEB_PAGE"])
    parser.add_argument("--family")
    parser.add_argument("--version", type=int, default=1)
    parser.add_argument("--output-dir", type=Path, help="Snapshot destination, e.g. fixtures/marketplace/<product_id>")
    args = parser.parse_args(argv)
    folders = [p.parent for p in (ROOT / "fixtures/real").rglob("product.json")
               if json.loads(p.read_text(encoding="utf-8")).get("product_id") == args.product]
    if len(folders) != 1:
        print("SKIP: exactly one matching product.json is required")
        return 1
    try:
        with httpx.Client() as client:
            path = capture_page(args.url, product=args.product, kind=args.kind, folder=folders[0],
                                client=client, family=args.family, version=args.version, output_folder=args.output_dir)
    except (httpx.HTTPError, CaptureError, OSError, UnicodeError) as exc:
        print(f"SKIP {args.url}: {type(exc).__name__}: {exc}")
        return 1
    print(path)
    for passage in json.loads(path.read_text(encoding="utf-8"))["passages"]:
        print(f"[{passage['locator']}] {passage['text']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
