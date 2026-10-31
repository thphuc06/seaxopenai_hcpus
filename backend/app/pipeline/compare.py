"""P1 comparison interfaces; implementation due at S1."""
from pydantic import JsonValue


def compatible(field: str, claim_value: JsonValue, ref_value: JsonValue) -> bool:
    raise NotImplementedError("P1 comparison due at S1")


def agree(field: str, a: JsonValue, b: JsonValue) -> bool:
    raise NotImplementedError("P1 agreement due at S1")


def same_volume(a: JsonValue, b: JsonValue, tol: float = 0.01) -> bool:
    raise NotImplementedError("P1 volume comparison due at S1")
