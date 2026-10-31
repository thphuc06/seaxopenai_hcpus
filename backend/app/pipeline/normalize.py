"""Pure normalization; open vocabulary is source-noted data, never code."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re
import math
import unicodedata

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class IngredientSeed(BaseModel):
    label: str
    surfaces: list[str]
    inci: list[str]


class SkinSeed(BaseModel):
    surfaces: list[str]
    values: list[str]


class Vocabulary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    about: str = Field(alias="_about")
    ingredients: list[IngredientSeed]
    skin: list[SkinSeed]
    field_labels: dict[str, list[str]]
    injection_patterns: list[str]
    sentence_abbreviations: list[str]
    negation_phrases: list[str]
    ingredient_separators: list[str]
    free_from: dict[str, list[str]]
    treatment_words: list[str]


class LegalForms(BaseModel):
    about: str = Field(alias="_about")
    forms: list[str]


@lru_cache(maxsize=1)
def vocabulary() -> Vocabulary:
    path = Path(__file__).parents[1] / "data/vocab_seed.json"
    return Vocabulary.model_validate_json(path.read_text(encoding="utf-8"))


def folded(text: str) -> str:
    text = unicodedata.normalize("NFD", text.casefold()).replace("đ", "d")
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def phrase_pattern(phrase: str) -> str:
    return r"(?<!\w)" + r"\s+".join(re.escape(word) for word in folded(phrase).split()) + r"(?!\w)"


def phrase_spans(text: str, phrase: str) -> list[tuple[int, int]]:
    """Match folded text while mapping locations back to the original spelling."""
    offsets = [index for index, character in enumerate(text) for _ in folded(character)]
    normalized = folded(text)
    spans: list[tuple[int, int]] = []
    for match in re.finditer(phrase_pattern(phrase), normalized):
        end = offsets[match.end() - 1] + 1
        while end < len(text) and unicodedata.category(text[end]) == "Mn":
            end += 1
        spans.append((offsets[match.start()], end))
    return spans


def skin_types_in(text: str) -> set[str]:
    if has_negation(text):
        return set()
    remaining = folded(text)
    found: set[str] = set()
    entries = [(surface, item.values) for item in vocabulary().skin for surface in item.surfaces]
    for surface, values in sorted(entries, key=lambda item: len(item[0]), reverse=True):
        pattern = phrase_pattern(surface)
        if re.search(pattern, remaining):
            found.update(values)
            remaining = re.sub(pattern, lambda match: " " * len(match[0]), remaining)
    return found


_VOLUME = re.compile(r"(?<![\w.,+\-])(?P<value>\d+(?:[.,]\d+)?)\s*(?P<unit>fl\s*\.?\s*oz\.?|ml|kg|g|l)(?!\w)", re.IGNORECASE)
_UNITS = {"ml": (1.0, "ml"), "l": (1000.0, "ml"), "g": (1.0, "g"), "kg": (1000.0, "g"), "floz": (29.5735, "ml")}


def volume_spans(text: str) -> list[tuple[str, dict[str, JsonValue]]]:
    result: list[tuple[str, dict[str, JsonValue]]] = []
    for match in _VOLUME.finditer(text):
        factor, unit = _UNITS[re.sub(r"[\s.]", "", match["unit"]).casefold()]
        value = float(match["value"].replace(",", ".")) * factor
        if math.isfinite(value) and value > 0:
            result.append((match[0], {"value": value, "unit": unit, "by": "code"}))
    return result


def volumes_in(text: str) -> list[dict[str, JsonValue]]:
    return [value for _, value in volume_spans(text)]


def parse_inci(text: str) -> list[str]:
    """Comma/semicolon/newline lists preserve periods inside INCI abbreviations."""
    return [part.strip() for part in re.split(r"[,;\n]+", text) if part.strip()]


def ingredient_keys(text: str, *, inci: bool = False) -> tuple[list[str], list[str]]:
    if inci:
        keys: list[str] = []
        for item in parse_inci(text):
            canonical = " ".join(item.casefold().rstrip(".").split())
            seed = next((entry for entry in vocabulary().ingredients
                         if canonical in {" ".join(name.casefold().rstrip(".").split()) for name in entry.inci}), None)
            keys.append(seed.label if seed else canonical.upper())
        return keys, []
    if has_negation(text):
        return [], []
    found: set[str] = set()
    unknown: list[str] = []
    separator_spans = [match.span() for match in re.finditer(r"[,;\n]+", text)]
    for word in vocabulary().ingredient_separators:
        separator_spans += (phrase_spans(text, word) if any(character.isalnum() for character in word)
                            else [match.span() for match in re.finditer(re.escape(word), text)])
    parts: list[str] = []
    start = 0
    for left, right in sorted(set(separator_spans)):
        if left >= start:
            parts.append(text[start:left])
            start = right
    parts.append(text[start:])
    for part in parts:
        remainder = part.strip().rstrip(".")
        entries = [(surface, entry.label) for entry in vocabulary().ingredients for surface in entry.surfaces]
        for surface, label in sorted(entries, key=lambda item: len(item[0]), reverse=True):
            matches = phrase_spans(remainder, surface)
            if matches:
                found.add(label)
                for left, right in reversed(matches):
                    remainder = remainder[:left] + " " + remainder[right:]
        remainder = re.sub(r"\b\d+(?:[.,]\d+)?\s*%", "", remainder).strip(" ()[]")
        if remainder:
            unknown.append(" ".join(remainder.split()))
    return sorted(found), unknown


def has_negation(text: str) -> bool:
    return any(re.search(phrase_pattern(phrase), folded(text)) for phrase in vocabulary().negation_phrases)


@lru_cache(maxsize=1)
def _legal_forms() -> list[str]:
    path = Path(__file__).parents[1] / "data/legal_forms.json"
    return LegalForms.model_validate_json(path.read_text(encoding="utf-8")).forms


def company_key(text: str) -> str:
    def clean(value: str) -> str:
        return " ".join(unicodedata.normalize("NFC", value).casefold().split())
    value = clean(text)
    for form in sorted((clean(form) for form in _legal_forms()), key=len, reverse=True):
        pattern = r"(?<!\w)" + r"\s+".join(re.escape(word) for word in form.split()) + r"(?!\w)"
        value = re.sub(pattern, " ", value)
    return " ".join(value.split()).strip("., ")


def normalize(field_key: str, raw_value: str | None, proposed: JsonValue = None) -> dict[str, JsonValue] | None:
    """`value` is canonical; list fields carry JSON lists, and every result has `by`."""
    if raw_value is None or not raw_value.strip():
        return None
    if field_key == "volume":
        values = volumes_in(raw_value)
        return values[0] if len(values) == 1 else None
    if field_key == "skin_type":
        values = sorted(skin_types_in(raw_value))
        return {"value": values, "by": "seed"} if values else None
    if field_key == "inci_list":
        keys, _ = ingredient_keys(raw_value, inci=True)
        return {"value": keys, "items": parse_inci(raw_value), "by": "seed"}
    if field_key == "key_ingredients":
        if has_negation(raw_value):
            return None
        keys, unknown = ingredient_keys(raw_value)
        return {"value": keys, "unknown": unknown, "by": "seed" if keys else "code"}
    if field_key == "responsible_company":
        value = company_key(raw_value)
        return {"value": value, "by": "code"} if value else None
    if field_key == "notification_number":
        value = re.sub(r"[\s\-–—]+", "", unicodedata.normalize("NFC", raw_value)).upper()
        return {"value": value, "by": "code"}
    raise ValueError("Unsupported normalization field")
