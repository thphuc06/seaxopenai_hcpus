"""P1 policy stub, implemented at S1; never manufactures a decision."""
from dataclasses import dataclass
from pydantic import JsonValue
from app.models import FieldDecision

POLICY_VERSION = "policy-v1"


@dataclass
class SourceObs:
    """P1 defines observation fields with policy implementation at S1."""


def decide(
    field_key: str, observations: list[SourceObs], product: dict[str, JsonValue],
    gaps: list[dict[str, JsonValue]], reviews: list[dict[str, JsonValue]],
) -> FieldDecision:
    raise NotImplementedError("P1 policy implementation due at S1")
