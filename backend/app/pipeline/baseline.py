"""B0 diagnostic comparison only. Never publishes findings or reads expected labels."""
from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import JsonValue

from app.models import PUBLIC_FIELDS, Readability, SourceKind, Verdict
from app.pipeline.compare import compatible
from app.pipeline.normalize import normalize

BASELINE_VERSION = "b0-v1"


@dataclass(frozen=True)
class BaselineClaim:
    source_kind: SourceKind
    field_key: str
    raw_value: str | None
    normalized: dict[str, JsonValue]
    readability: Readability = Readability.READABLE


@dataclass(frozen=True)
class BaselineFinding:
    field_key: str
    verdict: Verdict
    seller_attributable: bool


def compare_claims(claims: Sequence[BaselineClaim]) -> list[BaselineFinding]:
    """Naive all-pairs listing/brand comparison; no scope, family or self-conflict rules.

    Stored canonical values are preferred. Missing canonical values use the same
    normalizer as the candidate. Packaging and notification sources are ignored.
    """
    findings: list[BaselineFinding] = []
    for field in PUBLIC_FIELDS:
        sides: dict[SourceKind, list[dict[str, JsonValue]]] = {
            SourceKind.LISTING: [], SourceKind.BRAND_PAGE: [],
        }
        for claim in claims:
            if claim.source_kind not in sides or claim.readability == Readability.UNREADABLE:
                continue
            if claim.field_key != field and not (field == "key_ingredients" and claim.field_key == "inci_list"):
                continue
            value = claim.normalized or normalize(claim.field_key, claim.raw_value)
            if value and compatible(field, value, value):
                sides[claim.source_kind].append(value)
        listing, reference = sides[SourceKind.LISTING], sides[SourceKind.BRAND_PAGE]
        if listing and reference:
            verdict = (Verdict.CONSISTENT if all(compatible(field, left, right)
                       for left in listing for right in reference) else Verdict.CONFLICTING)
        else:
            verdict = Verdict.SINGLE_SOURCE if listing or reference else Verdict.INSUFFICIENT
        findings.append(BaselineFinding(field, verdict, verdict == Verdict.CONFLICTING))
    return findings
