"""P2 owns extraction; fallback at S1 and model extraction at S2."""
from dataclasses import dataclass
from pydantic import JsonValue
from app.context import RunContext
from app.models import Readability


@dataclass
class Claim:
    id: str
    source_version_id: str
    passage_id: str
    field_key: str
    raw_value: str | None
    normalized: dict[str, JsonValue]
    quote: str | None
    readability: Readability
    extractor: str
    prompt_version: str
    mapped_by: str


@dataclass
class Extraction:
    claims: list[Claim]
    ignored_instructions: bool
    extractor: str
    cached: bool


def extract_source_version(sv_id: str, ctx: RunContext) -> Extraction:
    return Extraction([], False, "FALLBACK", False)
