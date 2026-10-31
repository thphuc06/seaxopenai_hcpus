"""Static P4-1c invariants; these checks never run a candidate or infer gold."""
from __future__ import annotations

import json
from pathlib import Path
from typing import TypeAlias, cast

from PIL import Image

ROOT = Path(__file__).resolve().parents[2] / "fixtures"
JSON: TypeAlias = str | int | float | bool | None | list["JSON"] | dict[str, "JSON"]


def read(relative: str) -> dict[str, JSON]:
    value = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, JSON], value)


def event_snapshot(name: str) -> dict[str, JSON]:
    event = read(f"events/{name}.json")
    return read(event["payload"]["snapshot"])


def test_story_events_and_gold_cover_every_checkpoint_in_order() -> None:
    gold = read("gold/dev/demo-story.json")
    assert len(gold["event_order"]) == 13
    assert [c["after_event"] for c in gold["checkpoints"]] == gold["event_order"]
    assert [name[:2] for name in gold["event_order"]] == [f"{n:02}" for n in range(1, 14)]
    for checkpoint in gold["checkpoints"]:
        event = read(f"events/{checkpoint['after_event']}.json")
        assert event["payload"]["product_id"] == checkpoint["product_id"]
        assert event["payload"]["case_id"] == checkpoint["case_id"]
        assert event["expect"]


def test_event_only_sources_cannot_enter_version_one_bootstrap() -> None:
    for name in ("04-volume-change", "05-revoke-notification", "06-evidence-added", "07-injection-listing", "09-catalogue-published", "10-blurred-label-photo"):
        event = read(f"events/{name}.json")
        path = ROOT / event["payload"]["snapshot"]
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        assert path.is_file()
        assert not path.name.endswith(".v1.json")
        assert snapshot["version"] == event["resource"]["version"] > 1
        assert snapshot["product_id"] == event["payload"]["product_id"]
        if event["resource"]["kind"] == "SOURCE":
            assert snapshot["source_id"] == event["resource"]["id"]


def test_catalogue_anchor_is_nearest_heading_in_same_section() -> None:
    catalogue = event_snapshot("09-catalogue-published")
    assert catalogue["scope"]["variant"] == "MULTI"
    passages = catalogue["passages"]
    row = next(p for p in passages if p["locator"] == "catalogue#50ml-skin")
    anchor = passages[passages.index(row) - 1]
    assert anchor["locator"] == "catalogue#50ml"
    assert row["section"] == anchor["section"]
    assert "50 ml" in anchor["text"]
    assert not any(char.isdigit() for char in row["text"])
    assert "mọi loại da" in row["text"] and "nhạy cảm" in row["text"]
    assert "da" not in anchor["text"].lower()


def test_all_packaging_images_exist_at_display_resolution() -> None:
    labels = []
    for path in (ROOT / "synthetic").rglob("*.json"):
        source = json.loads(path.read_text(encoding="utf-8"))
        if source.get("kind") != "PACKAGING_IMAGE":
            continue
        labels.append(path)
        with Image.open(path.with_suffix(".png")) as image:
            assert image.format == "PNG"
            assert image.size == (1280, 720)
            image.verify()
    assert len(labels) == 5


def test_full_story_blur_is_additive_and_isolated_case_is_explicit() -> None:
    blurred = event_snapshot("10-blurred-label-photo")
    clear = read("synthetic/s1-gentle-cleanser/packaging_label.v1.json")
    assert blurred["source_id"] != clear["source_id"]
    assert all(not passage["text"] for passage in blurred["passages"])
    assert all(passage["text"] for passage in clear["passages"])
    gold = read("gold/dev/demo-story.json")
    before, after = gold["checkpoints"][8:10]
    assert before["expected"] == after["expected"]
    assert set(gold["isolated_scenarios"][0]["expected"].values()) == {"INSUFFICIENT"}


def test_registry_has_four_planned_records_and_sun_has_no_seed_document() -> None:
    records = read("synthetic/registry/mock_registry.json")["records"]
    assert {key: row["status"] for key, row in records.items()} == {
        "DEMO-CBMP-00042": "REVOKED", "DEMO-CBMP-00077": "ACTIVE",
        "DEMO-CBMP-00088": "ACTIVE", "DEMO-CBMP-00123": "ACTIVE",
    }
    for path in (ROOT / "synthetic/s3-sun-fluid").glob("*.v1.json"):
        assert json.loads(path.read_text(encoding="utf-8"))["kind"] not in {"NOTIFICATION_DOC", "REGISTRY_RECORD"}


def test_serum_copy_and_claim_order_are_present_in_stored_passages() -> None:
    listing = read("synthetic/s4-clear-serum/listing.v1.json")
    brand = read("synthetic/s4-clear-serum/brand.v1.json")
    listing_skin = next(p["text"] for p in listing["passages"] if p["locator"] == "usage#skin")
    brand_skin = next(p["text"] for p in brand["passages"] if p["locator"] == "usage#skin")
    assert listing_skin == brand_skin and len(listing_skin) >= 30
    label = read("synthetic/s4-clear-serum/packaging_label.v1.json")["passages"][0]["text"]
    assert label.index("Phenoxyethanol") < label.index("Niacinamide")
    assert "Alcohol Denat." in label and "Parfum" in label


def test_gold_variants_and_claims_cite_exact_stored_passages() -> None:
    def visit(value: object) -> None:
        if isinstance(value, dict):
            if "snapshot" in value and "passage_id" in value:
                source = read(value["snapshot"])
                passage = next(p for p in source["passages"] if p["id"] == value["passage_id"])
                assert source["source_id"] == value["source_id"]
                assert passage["locator"] == value["locator"]
                assert value["excerpt"] in passage["text"]
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(read("gold/dev/demo-story.json"))
