"""P2 normalization interfaces; implementation due at S1."""
from pydantic import JsonValue


def normalize(field_key: str, raw_value: str | None, proposed: JsonValue = None) -> dict[str, JsonValue] | None:
    raise NotImplementedError("P2 normalization due at S1")


def volumes_in(text: str) -> list[dict[str, JsonValue]]:
    raise NotImplementedError("P2 volume parser due at S1")


def skin_types_in(text: str) -> set[str]:
    raise NotImplementedError("P2 skin parser due at S1")


def parse_inci(text: str) -> list[str]:
    raise NotImplementedError("P2 INCI parser due at S1")


def company_key(text: str) -> str:
    raise NotImplementedError("P2 company normalization due at S1")
