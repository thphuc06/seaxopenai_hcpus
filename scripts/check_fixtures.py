"""Read-only dataset format checks; no pipeline execution or label inference."""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))
from app.models import DatasetOrigin, EventEnvelope, SourceKind, SourceStatus

Nonempty = Annotated[str, Field(min_length=1, pattern=r"\S")]


class FixtureModel(BaseModel):
    # Source metadata may grow; the documented core remains required and typed.
    model_config = ConfigDict(extra="allow")


class Product(FixtureModel):
    product_id: Nonempty
    name: Nonempty
    brand: Nonempty
    variant: Nonempty
    market: Nonempty
    dataset_origin: DatasetOrigin
    case_id: Nonempty
    tenant_id: Nonempty
    listing_id: Nonempty


class Passage(FixtureModel):
    id: Nonempty
    locator: Nonempty
    section: Nonempty
    text: str


class Scope(FixtureModel):
    product: Nonempty
    variant: Nonempty | None
    market: Nonempty
    version: Nonempty


class Snapshot(FixtureModel):
    source_id: Nonempty
    kind: SourceKind
    product_id: Nonempty
    version: int = Field(ge=1, strict=True)
    uri: Nonempty
    captured_at: Nonempty
    dataset_origin: DatasetOrigin
    visibility: Literal["PUBLIC", "PRIVATE"]
    family: Nonempty
    scope: Scope | None = None
    passages: list[Passage] = Field(min_length=1)
    status: SourceStatus = SourceStatus.ACTIVE
    note: str = ""


@dataclass
class FileCheck:
    path: Path
    problems: list[str] = field(default_factory=list)


def _read_object(path: Path, check: FileCheck) -> dict[str, object] | None:
    try:
        text = path.read_text(encoding="utf-8")
        if "TODO" in text:
            check.problems.append("uppercase TODO marker")
        value = json.loads(text)
        if "TODO" not in text and "TODO" in json.dumps(value, ensure_ascii=False):
            check.problems.append("uppercase TODO marker")
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        check.problems.append(f"cannot read JSON: {exc}")
        return None
    if not isinstance(value, dict):
        check.problems.append("JSON root must be an object")
        return None
    return value


def _schema_errors(exc: ValidationError) -> list[str]:
    return [f"{'.'.join(map(str, item['loc']))}: {item['msg']}" for item in exc.errors(include_input=False)]


def _check_timestamp(value: str, name: str, check: FileCheck) -> None:
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError("timezone required")
    except ValueError:
        check.problems.append(f"{name}: expected ISO-8601 timestamp with timezone")


def _check_snapshot(
    path: Path, data: dict[str, object], check: FileCheck,
    products: dict[str, tuple[Path, Product]], passages: dict[tuple[str, str], Path],
    versions: dict[tuple[str, int], Path], root: Path,
) -> None:
    try:
        snapshot = Snapshot.model_validate(data)
    except ValidationError as exc:
        check.problems.extend(_schema_errors(exc))
        return
    _check_timestamp(snapshot.captured_at, "captured_at", check)
    product_entry = products.get(snapshot.product_id)
    if product_entry is None:
        check.problems.append("product.json missing or invalid for product_id")
    elif not path.is_relative_to(root / "marketplace") and path.parent != product_entry[0].parent:
        check.problems.append("product.json must be present in snapshot folder")
    if snapshot.dataset_origin == DatasetOrigin.SYNTHETIC and snapshot.scope is None:
        check.problems.append("synthetic snapshot requires scope")
    version_key = (snapshot.source_id, snapshot.version)
    if version_key in versions:
        check.problems.append(f"duplicate source version, also in {versions[version_key].relative_to(root)}")
    versions[version_key] = path
    for passage in snapshot.passages:
        key = (snapshot.product_id, passage.id)
        if key in passages:
            check.problems.append(f"duplicate passage id {passage.id}, also in {passages[key].relative_to(root)}")
        passages[key] = path
        if not passage.text.strip():
            # Phase 0 allows readable transcripts before PNG generation, never empty placeholders.
            image = path.with_suffix(".png")
            if snapshot.kind != SourceKind.PACKAGING_IMAGE or not image.is_file() or not snapshot.note.strip():
                check.problems.append(f"empty passage {passage.id}: requires packaging PNG and explanatory note")
            else:
                try:
                    with Image.open(image) as png:
                        if png.format != "PNG":
                            raise ValueError("expected PNG")
                        png.verify()
                except (OSError, ValueError, SyntaxError):
                    check.problems.append(f"empty passage {passage.id}: sibling PNG is not a readable image file")


def _check_event(path: Path, data: dict[str, object], check: FileCheck, root: Path) -> None:
    if not isinstance(data.get("expect"), str) or not str(data["expect"]).strip():
        check.problems.append("expect: nonempty caption required")
    try:
        event = EventEnvelope.model_validate({key: value for key, value in data.items() if key != "expect"})
    except ValidationError as exc:
        check.problems.extend(_schema_errors(exc))
        return
    _check_timestamp(event.occurred_at, "occurred_at", check)
    if "snapshot" in event.payload:
        relative = event.payload["snapshot"]
        if not isinstance(relative, str) or not relative.strip():
            check.problems.append("payload.snapshot must be a nonempty relative path")
        else:
            target = (root / relative).resolve()
            if Path(relative).is_absolute() or not target.is_relative_to(root):
                check.problems.append("payload.snapshot must stay within fixtures/")
            elif not target.is_file():
                check.problems.append(f"payload.snapshot does not exist: {relative}")


def check_fixtures(root: Path) -> list[FileCheck]:
    """Validate existing catalogue groups and events without writing any files."""
    root = root.resolve()
    if not root.is_dir():
        return [FileCheck(root, ["fixtures directory does not exist"])]
    paths = sorted(path for group in ("synthetic", "real", "blind", "marketplace", "events")
                   for path in (root / group).rglob("*.json"))
    if not paths:
        return [FileCheck(root, ["no fixture JSON found"])]
    checks = {path: FileCheck(path) for path in paths}
    objects = {path: _read_object(path, checks[path]) for path in paths}
    products: dict[str, tuple[Path, Product]] = {}
    for path, data in objects.items():
        if path.name != "product.json" or data is None:
            continue
        try:
            product = Product.model_validate(data)
        except ValidationError as exc:
            checks[path].problems.extend(_schema_errors(exc))
            continue
        if product.product_id in products:
            checks[path].problems.append("duplicate product_id")
        products[product.product_id] = (path, product)
    passages: dict[tuple[str, str], Path] = {}
    versions: dict[tuple[str, int], Path] = {}
    for path, data in objects.items():
        if data is None or path.name == "product.json":
            continue
        check = checks[path]
        if path.is_relative_to(root / "events"):
            _check_event(path, data, check, root)
        elif "registry" in data and "records" in data:
            # The separately documented registry map is not a source snapshot.
            if not isinstance(data["registry"], str) or not isinstance(data["records"], dict) or not isinstance(data.get("warning"), str):
                check.problems.append("invalid registry map: registry/warning strings and records object required")
        else:
            _check_snapshot(path, data, check, products, passages, versions, root)
    return list(checks.values())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=REPO_ROOT / "fixtures")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    checks = check_fixtures(root)
    print("path | problems")
    for check in checks:
        label = str(check.path.relative_to(root)) if check.path.is_relative_to(root) else str(check.path)
        print(f"{label} | {'; '.join(check.problems) if check.problems else 'OK'}")
    failed = sum(bool(check.problems) for check in checks)
    print(f"{len(checks)} files checked; {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
