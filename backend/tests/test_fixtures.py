"""P4 checks format failures with unrelated temporary products, never pipeline outputs."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys

from PIL import Image
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.check_fixtures import check_fixtures, main
from test_guards import FORBIDDEN

pytestmark = pytest.mark.phase(0)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def catalogue(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    root = tmp_path / "fixtures"
    folder = root / "synthetic" / "unrelated-lotion"
    product = {
        "product_id": "sample-product", "name": "Sample Lotion", "brand": "Example Lab",
        "variant": "85ml", "market": "SG", "dataset_origin": "SYNTHETIC",
        "case_id": "sample-case", "tenant_id": "sample-tenant", "listing_id": "sample-listing",
    }
    snapshot = {
        "source_id": "sample-source", "kind": "LISTING", "product_id": "sample-product",
        "version": 1, "uri": "demo://sample", "captured_at": "2026-10-31T03:00:00Z",
        "dataset_origin": "SYNTHETIC", "visibility": "PUBLIC", "family": "seller:sample",
        "scope": {"product": "sample-product", "variant": "85ml", "market": "SG", "version": "1"},
        "passages": [{"id": "sample-passage", "locator": "title", "section": "overview", "text": "Sample lotion, 85 ml."}],
    }
    write_json(folder / "product.json", product)
    path = folder / "listing.v1.json"
    write_json(path, snapshot)
    return root, path, snapshot


def problems(root: Path) -> str:
    return "\n".join(problem for check in check_fixtures(root) for problem in check.problems)


def test_repository_fixtures_valid_in_process(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(ROOT / "fixtures")]) == 0
    assert "0 failed" in capsys.readouterr().out


def test_unrelated_product_valid_and_validator_is_read_only(catalogue: tuple[Path, Path, dict[str, object]]) -> None:
    root, _, _ = catalogue
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert problems(root) == ""
    assert {p: p.read_bytes() for p in root.rglob("*") if p.is_file()} == before


@pytest.mark.parametrize("key,value,expected", [
    ("kind", "NOT_A_KIND", "kind"),
    ("dataset_origin", "REPLAY", "dataset_origin"),
    ("version", True, "version"),
    ("version", 0, "version"),
    ("captured_at", "yesterday", "captured_at"),
    ("captured_at", "2026-10-31T03:00:00", "timezone"),
    ("family", " ", "family"),
    ("scope", None, "requires scope"),
    ("product_id", "missing-product", "product.json"),
    ("note", "TODO capture", "uppercase TODO"),
])
def test_invalid_snapshot_fields(
    catalogue: tuple[Path, Path, dict[str, object]], key: str, value: object, expected: str,
) -> None:
    root, path, snapshot = catalogue
    write_json(path, {**snapshot, key: value})
    assert expected in problems(root)


def test_missing_required_key_and_product(catalogue: tuple[Path, Path, dict[str, object]]) -> None:
    root, path, snapshot = catalogue
    del snapshot["source_id"]
    write_json(path, snapshot)
    assert "source_id" in problems(root)
    path.with_name("product.json").unlink()
    snapshot["source_id"] = "sample-source"
    write_json(path, snapshot)
    assert "product.json" in problems(root)


@pytest.mark.parametrize("across_files", [False, True])
def test_duplicate_passages_per_file_and_product(
    catalogue: tuple[Path, Path, dict[str, object]], across_files: bool,
) -> None:
    root, path, snapshot = catalogue
    if across_files:
        write_json(path.with_name("other.v1.json"), {**snapshot, "source_id": "other-source"})
    else:
        snapshot["passages"] = [*snapshot["passages"], *snapshot["passages"]]
        write_json(path, snapshot)
    assert "duplicate passage id" in problems(root)


@pytest.mark.parametrize("kind", ["LISTING", "PACKAGING_IMAGE"])
def test_empty_passage_needs_image_and_note(
    catalogue: tuple[Path, Path, dict[str, object]], kind: str,
) -> None:
    root, path, snapshot = catalogue
    snapshot["kind"] = kind
    snapshot["passages"][0]["text"] = ""
    write_json(path, snapshot)
    assert "empty passage" in problems(root)
    Image.new("RGB", (2, 2), "gray").save(path.with_suffix(".png"))
    assert "empty passage" in problems(root)
    snapshot["note"] = "Intentionally unreadable photo for a format test."
    write_json(path, snapshot)
    if kind == "PACKAGING_IMAGE":
        assert problems(root) == ""
        path.with_suffix(".png").write_bytes(b"not an image")
        assert "not a readable image" in problems(root)
    else:
        assert "empty passage" in problems(root)


def test_readable_transcript_can_precede_png_and_lowercase_marker_is_allowed(
    catalogue: tuple[Path, Path, dict[str, object]],
) -> None:
    root, path, snapshot = catalogue
    write_json(path, {**snapshot, "kind": "PACKAGING_IMAGE", "image_todo": "Phase 1 image"})
    assert problems(root) == ""


def event(snapshot: str) -> dict[str, object]:
    return {
        "event_id": "test-event", "idempotency_key": "sample:v2", "type": "SOURCE_CHANGED",
        "schema_version": "1", "producer": "publisher-panel",
        "resource": {"kind": "SOURCE", "id": "sample-source", "version": 2},
        "changed_fields": ["volume"], "payload": {"snapshot": snapshot},
        "occurred_at": "2026-10-31T03:00:00Z", "correlation_id": "sample-flow", "expect": "Reassess source.",
    }


@pytest.mark.parametrize("relative,expected", [
    ("synthetic/unrelated-lotion/listing.v1.json", ""),
    ("synthetic/missing.json", "does not exist"),
    ("../outside.json", "stay within"),
    ("", "nonempty relative path"),
])
def test_snapshot_paths_resolve_from_fixture_root(
    catalogue: tuple[Path, Path, dict[str, object]], relative: str, expected: str,
) -> None:
    root, _, _ = catalogue
    write_json(root / "events" / "change.json", event(relative))
    actual = problems(root)
    assert expected in actual if expected else actual == ""


def test_event_schema_errors_and_cli_failure(catalogue: tuple[Path, Path, dict[str, object]]) -> None:
    root, _, _ = catalogue
    data = event("synthetic/unrelated-lotion/listing.v1.json")
    data["type"] = "UNKNOWN"
    del data["expect"]
    write_json(root / "events" / "bad.json", data)
    assert "type" in problems(root)
    assert "expect" in problems(root)
    assert main([str(root)]) == 1


@pytest.mark.parametrize("text", ["{broken", "[]", '{"note":"\\u0054ODO"}'])
def test_malformed_or_nonobject_json_is_reported(tmp_path: Path, text: str) -> None:
    path = tmp_path / "synthetic" / "invalid.json"
    path.parent.mkdir()
    path.write_text(text, encoding="utf-8")
    assert problems(tmp_path)


def test_marketplace_resolves_catalogue_and_real_scope_can_be_absent(
    catalogue: tuple[Path, Path, dict[str, object]],
) -> None:
    root, _, snapshot = catalogue
    other = copy.deepcopy(snapshot)
    other.update(source_id="retailer-page", dataset_origin="REAL", kind="WEB_PAGE")
    del other["scope"]
    other["passages"][0]["id"] = "retailer-passage"
    write_json(root / "marketplace" / "sample-product" / "shop.json", other)
    assert problems(root) == ""


def test_synthetic_source_wording_uses_shared_guard() -> None:
    for path in (ROOT / "fixtures/synthetic").rglob("*.json"):
        assert not FORBIDDEN.search(path.read_text(encoding="utf-8")), path


def test_draft_gold_has_stored_evidence_and_event_replay_key() -> None:
    root = ROOT / "fixtures"
    gold = json.loads((root / "gold/dev/demo-story.json").read_text(encoding="utf-8"))
    assert gold["status"] in {"DRAFT", "REVIEWED"}
    if gold["status"] == "REVIEWED":
        assert gold["reviewed_by"] and gold["reviewed_at"]
    for checkpoint in gold["checkpoints"]:
        assert set(checkpoint["expected"]) == set(checkpoint["rationale"])
        for row in checkpoint["rationale"].values():
            assert row["rationale"] and row["evidence"]
            for citation in row["evidence"]:
                source = json.loads((root / citation["snapshot"]).read_text(encoding="utf-8"))
                passage = next(p for p in source["passages"] if p["id"] == citation["passage_id"])
                assert source["source_id"] == citation["source_id"]
                assert passage["locator"] == citation["locator"]
                assert citation["excerpt"] in passage["text"]
    events = [json.loads((root / "events" / filename).read_text(encoding="utf-8")) for filename in (
        "02-price-change.json", "03-duplicate-price-change.json",
    )]
    assert events[0]["idempotency_key"] == events[1]["idempotency_key"]
    assert events[0]["payload"] == events[1]["payload"]
