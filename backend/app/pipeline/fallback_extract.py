"""Deterministic claims from generic field cues and source-noted vocabulary."""
from __future__ import annotations

import re

from pydantic import BaseModel

from app.models import ClaimExtraction, ExtractedClaim
from app.pipeline.normalize import folded, has_negation, ingredient_keys, phrase_pattern, phrase_spans, skin_types_in, vocabulary, volume_spans

FALLBACK_VERSION = "fallback-v2"


class Passage(BaseModel):
    id: str
    source_version_id: str
    locator: str
    section: str | None
    text: str


def sentence_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start = 0
    abbreviations = {folded(word) for word in vocabulary().sentence_abbreviations}
    for boundary in re.finditer(r"[.!?](?=\s|<|$)|\n+", text):
        token = re.search(r"[\w.]+$", text[:boundary.end()])
        if boundary[0] == "." and token and folded(token[0]) in abbreviations:
            continue
        spans.append((start, boundary.end()))
        start = boundary.end()
    if start < len(text):
        spans.append((start, len(text)))
    return spans


def injection_spans(text: str) -> list[tuple[int, int]]:
    return [(left, right) for left, right in sentence_spans(text)
            if any(re.search(phrase_pattern(pattern), folded(text[left:right]))
                   for pattern in vocabulary().injection_patterns)]


def clean_regions(text: str) -> list[str]:
    start = 0
    regions: list[str] = []
    for left, right in injection_spans(text):
        regions.append(text[start:left])
        start = right
    regions.append(text[start:])
    return [region.strip() for region in regions if region.strip()]


def _claim(field: str, raw: str, passage: Passage, quote: str | None = None) -> ExtractedClaim:
    return ExtractedClaim(field_key=field, raw_value=raw, passage_id=passage.id,
                          quote=raw if quote is None else quote, readability="READABLE",
                          proposed_skin_types=None, proposed_ingredients=None, proposed_volume_ml=None)


def _label_field(head: str) -> str | None:
    candidates = [(label, field) for field, labels in vocabulary().field_labels.items() for label in labels]
    for label, field in sorted(candidates, key=lambda item: len(item[0]), reverse=True):
        if re.search(phrase_pattern(label), folded(head)):
            return field
    return None


def _labelled(line: str) -> tuple[str, str] | None:
    head, separator, tail = line.partition(":")
    field = _label_field(head) if separator else None
    if field is None or not tail.strip():
        return None
    # Keep INCI periods (Denat., Ext.); other field sentence punctuation is not value data.
    return field, tail.strip() if field == "inci_list" else tail.strip().rstrip(".")


def _label_chunks(line: str) -> list[str]:
    """A new labeled field ends the prior value even after a company abbreviation."""
    starts: set[int] = set()
    for labels in vocabulary().field_labels.values():
        for label in labels:
            for left, right in phrase_spans(line, label):
                colon = line.find(":", right)
                if colon >= 0 and not re.search(r"[.:;\n]", line[right:colon]):
                    starts.add(left)
    # Nested cue aliases must not split a single header into several values.
    boundaries: list[int] = []
    last_colon = -1
    for start in sorted(starts):
        if start > last_colon:
            boundaries.append(start)
            last_colon = line.find(":", start)
    if len(boundaries) <= 1:
        return [line]
    boundaries[0] = 0
    return [line[left:right].strip(" .;") for left, right in zip(boundaries, boundaries[1:] + [len(line)])]


def _extraction_chunks(text: str) -> list[str]:
    """Keep wrapped INCI text contiguous; headers and paragraphs end a list."""
    spans = sentence_spans(text)
    chunks: list[str] = []
    index = 0
    while index < len(spans):
        left, right = spans[index]
        head, separator, _ = text[left:right].partition(":")
        if separator and _label_field(head) == "inci_list":
            while index + 1 < len(spans):
                next_left, next_right = spans[index + 1]
                previous = text[spans[index][0]:right]
                following = text[next_left:next_right]
                # A sentence boundary is punctuation; a soft line wrap ends in
                # exactly one newline. Blank lines and any new header stop it.
                if (not previous.endswith("\n") or re.search(r"\n\s*\n$", previous)
                        or not following.strip() or ":" in following
                        or volume_spans(following) or skin_types_in(following) or has_negation(following)):
                    break
                index += 1
                right = next_right
        chunks.extend(_label_chunks(text[left:right]))
        index += 1
    return chunks


def extract(sv_id: str, passages: list[Passage]) -> ClaimExtraction:
    claims: list[ExtractedClaim] = []
    ignored = any(injection_spans(passage.text) for passage in passages)
    for passage in passages:
        for region in clean_regions(passage.text):
            lines = _extraction_chunks(region)
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                labelled = _labelled(line)
                if labelled:
                    field, value = labelled
                    claims.append(_claim(field, value, passage))
                    if field in {"inci_list", "notification_number", "responsible_company", "key_ingredients"}:
                        continue
                for raw, _ in volume_spans(line):
                    claims.append(_claim("volume", raw, passage))
                if skin_types_in(line):
                    claims.append(_claim("skin_type", line, passage))
                if ingredient_keys(line)[0]:
                    claims.append(_claim("key_ingredients", line, passage))
    return ClaimExtraction(source_version_id=sv_id, claims=claims, ignored_instructions_detected=ignored)
