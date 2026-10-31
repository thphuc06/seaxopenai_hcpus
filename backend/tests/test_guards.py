"""Repository guards. Vocabulary is from docs/06; fixture identifiers are discovered."""
from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import subprocess
from collections.abc import Iterator

import pytest

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN = re.compile(
    r"\b(?:genuine|authentic|fake|counterfeit|safe|certified|verified product|chính hãng|hàng giả|an toàn)\b",
    re.IGNORECASE,
)
KEY_PATTERN = re.compile(rb"sk-[A-Za-z0-9_-]{16,}")
pytestmark = pytest.mark.phase(0)


def application_files() -> Iterator[Path]:
    for folder in (ROOT / "backend/app", ROOT / "frontend/src"):
        if folder.exists():
            yield from (p for p in folder.rglob("*") if p.suffix in {".py", ".ts", ".tsx", ".js", ".jsx", ".json"})


def string_literals(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".py":
        return [node.value for node in ast.walk(ast.parse(text)) if isinstance(node, ast.Constant) and isinstance(node.value, str)]
    if path.suffix == ".json":
        def strings(value: object) -> Iterator[str]:
            if isinstance(value, str):
                yield value
            elif isinstance(value, list):
                for item in value:
                    yield from strings(item)
            elif isinstance(value, dict):
                for key, item in value.items():
                    yield str(key)
                    yield from strings(item)
        return list(strings(json.loads(text)))
    # Include JSX text as well as JS/TS quoted strings and template literals.
    quoted = re.findall(r"(['\"`])((?:\\.|(?!\1).)*?)\1", text, flags=re.DOTALL)
    jsx = re.findall(r">([^<>{}]+)<", text)
    return [body for _, body in quoted] + jsx


def test_no_gold_access_from_application() -> None:
    violations: list[str] = []
    for path in (ROOT / "backend/app").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                value = node.value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    if "fixtures/gold" in value.value.replace("\\", "/").lower():
                        violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [alias.name for alias in node.names]
                if isinstance(node, ast.ImportFrom):
                    names.append(node.module or "")
                if any("fixtures.gold" in name for name in names):
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
            # Inspect path expressions and I/O calls, not prose docstrings.
            if isinstance(node, (ast.Call, ast.BinOp, ast.Subscript)):
                parts = [n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
                joined = "/".join(parts).replace("\\", "/").lower()
                if "fixtures/gold" in joined or "gold" in parts:
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not violations, "Application references offline labels: " + ", ".join(violations)


def test_no_forbidden_wording_in_application_strings() -> None:
    violations = [
        str(path.relative_to(ROOT))
        for path in application_files()
        # A literal defining this exact guard pattern is not product wording.
        if any(FORBIDDEN.search(value) for value in string_literals(path) if value != FORBIDDEN.pattern)
    ]
    assert not violations, "Wording guard: " + ", ".join(violations)


def fixture_tokens(value: object) -> Iterator[str]:
    if isinstance(value, list):
        for item in value:
            yield from fixture_tokens(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, str):
                if key in {"brand", "brand_name"} and item.strip():
                    yield item
                elif key in {"product_id", "case_id", "source_id"} and item.strip():
                    yield item
                elif key in {"passage_id", "id"}:
                    if len(item) >= 6 and any(char.isdigit() for char in item):
                        yield item
            yield from fixture_tokens(item)


def test_no_fixture_identifiers_or_brands_in_application() -> None:
    tokens: set[str] = set()
    for path in (ROOT / "fixtures").rglob("*.json"):
        tokens.update(fixture_tokens(json.loads(path.read_text(encoding="utf-8"))))
    violations: list[str] = []
    for path in application_files():
        if path.is_relative_to(ROOT / "frontend/src/mock"):
            continue
        text = path.read_text(encoding="utf-8").casefold()
        if any(token.casefold() in text for token in tokens):
            violations.append(str(path.relative_to(ROOT)))
    assert not violations, "Fixture hardcoding: " + ", ".join(violations)


def test_no_tracked_env_or_key_material() -> None:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True,
    )
    paths = [name.decode("utf-8") for name in result.stdout.split(b"\0") if name]
    assert "backend/.env" not in paths
    violations = [name for name in paths if (ROOT / name).is_file() and KEY_PATTERN.search((ROOT / name).read_bytes())]
    assert not violations, "Key-shaped content in: " + ", ".join(violations)
