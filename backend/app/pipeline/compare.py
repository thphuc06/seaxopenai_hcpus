"""Comparison of normalized values only; raw text belongs to P2 normalization."""
import math
from collections.abc import Sequence
from pydantic import JsonValue


def members(value: JsonValue) -> frozenset[str]:
    if isinstance(value, dict):
        value = value.get("types", value.get("ingredients", value.get("value")))
    if isinstance(value, str):
        return frozenset([value])
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return frozenset(value)
    return frozenset()


def scalar(value: JsonValue) -> JsonValue:
    return value.get("value") if isinstance(value, dict) else value


def has_value(field: str, value: JsonValue) -> bool:
    """Unknown/empty normalized values cannot contribute evidence or votes."""
    return bool(value) and (bool(members(value)) if field in {"skin_type", "key_ingredients"}
                            else scalar(value) not in (None, ""))


def compatible(field: str, claim_value: JsonValue, ref_value: JsonValue) -> bool:
    """Directional: reference must support every element of the listing claim."""
    if field == "volume":
        return same_volume(claim_value, ref_value)
    if field in {"skin_type", "key_ingredients", "inci_list"}:
        claim, reference = members(claim_value), members(ref_value)
        return bool(claim and reference) and (field == "skin_type" and "ALL" in reference or claim <= reference)
    left, right = scalar(claim_value), scalar(ref_value)
    return left is not None and left != "" and left == right


def agree(field: str, a: JsonValue, b: JsonValue) -> bool:
    """Symmetric agreement between two reference statements."""
    return compatible(field, a, b) or compatible(field, b, a)


def source_values(field: str, values: Sequence[JsonValue]) -> list[JsonValue]:
    """Positive ingredient highlights combine; other values keep their statements."""
    if field == "key_ingredients":
        return [{"value": sorted(set().union(*(members(value) for value in values)))}]
    return list(values)


def same_volume(a: JsonValue, b: JsonValue, tol: float = 0.01) -> bool:
    if (not isinstance(a, dict) or not isinstance(b, dict) or a.get("unit") not in {"ml", "g"}
            or a.get("unit") != b.get("unit")):
        return False
    x, y = a.get("value"), b.get("value")
    if isinstance(x, bool) or isinstance(y, bool) or not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        return False
    return (math.isfinite(x) and math.isfinite(y) and x > 0 and y > 0
            and math.isfinite(tol) and tol >= 0 and abs(x - y) <= min(x, y) * tol)
