"""Pure R3 scope inference and R7c copy signals; policy owns public decisions."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
import re
from pathlib import Path
import unicodedata
from urllib.parse import urlsplit

from pydantic import JsonValue

from app.models import ScopeMatch, SourceKind
from app.pipeline import compare, normalize

Record = Mapping[str, JsonValue]
Passage = str | Record


@dataclass(frozen=True)
class MarketRules:
    country_tlds: frozenset[str]
    generic_cctlds: frozenset[str]


@dataclass(frozen=True)
class ScopeTextRules:
    gift_markers: tuple[str, ...]
    indirect_markers: tuple[str, ...]


def load_scope_text_rules(path: Path | None = None) -> ScopeTextRules | None:
    path = path or Path(__file__).parents[1] / "data/scope_text_rules.json"
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("_about"),str) or not value["_about"].strip():
        raise ValueError("Scope text rules require a source note")
    arrays: dict[str, tuple[str,...]] = {}
    for key in ("gift_markers","indirect_markers"):
        markers = value.get(key)
        if not isinstance(markers,list) or not markers or not all(isinstance(item,str) and item.strip() for item in markers):
            raise ValueError("Scope text markers must be nonblank strings")
        arrays[key] = tuple(markers)
    return ScopeTextRules(arrays["gift_markers"],arrays["indirect_markers"])


def _volume_roles(text: str, rules: ScopeTextRules) -> list[tuple[str, dict[str, JsonValue], ScopeMatch]]:
    volumes = normalize.volume_spans(text)
    offsets: list[int] = []
    cursor = 0
    for raw,_ in volumes:
        start = text.index(raw,cursor)
        offsets.append(start)
        cursor = start+len(raw)
    roles = [ScopeMatch.MATCH]*len(volumes)
    markers: list[tuple[int,int]] = []
    for start,end in sorted({span for cue in rules.gift_markers for span in normalize.phrase_spans(text,cue)}):
        if markers and not text[markers[-1][1]:start].strip():
            markers[-1] = (markers[-1][0],max(markers[-1][1],end))
        else:
            markers.append((start,end))
    boundaries = [m.start() for m in re.finditer(r"[;\n!?]|(?<!\d)\.(?=\s|$)",text)]
    for start,end in markers:
        stop = min([p for p in boundaries if p >= end]+[p for p,_ in markers if p > start]+[len(text)])
        clause_start = max([p+1 for p in boundaries if p < start]+[0])
        following = [i for i,offset in enumerate(offsets) if end <= offset < stop]
        indirect = normalize.has_negation(text[clause_start:stop]) or any(
            normalize.phrase_spans(text[end:stop],cue) for cue in rules.indirect_markers)
        # Never pick the quantity matching the case from ambiguous promotional wording.
        for index in following:
            roles[index] = ScopeMatch.MISMATCH if len(following) == 1 and not indirect else ScopeMatch.UNKNOWN
        if not following:
            preceding = [i for i,offset in enumerate(offsets) if clause_start <= offset < start]
            if preceding:
                roles[preceding[-1]] = ScopeMatch.UNKNOWN
    return [(raw,value,role) for (raw,value),role in zip(volumes,roles)]


def volume_claim_scope(text: str, value: Record, *, text_rules: ScopeTextRules | None = None) -> tuple[ScopeMatch, str]:
    rules = text_rules if text_rules is not None else load_scope_text_rules()
    if rules is None:
        return ScopeMatch.UNKNOWN, "Scope text rules are unavailable"
    if not any(normalize.phrase_spans(text,cue) for cue in rules.gift_markers):
        return ScopeMatch.MATCH, "No marked gift context"
    roles = {role for _,candidate,role in _volume_roles(text,rules) if compare.same_volume(candidate,dict(value))}
    if roles == {ScopeMatch.MISMATCH}:
        return ScopeMatch.MISMATCH, "GIFT_CONTEXT: quantity belongs to an explicitly marked gift"
    if roles == {ScopeMatch.MATCH}:
        return ScopeMatch.MATCH, "Quantity is outside marked gift context"
    return ScopeMatch.UNKNOWN, "AMBIGUOUS_VOLUME_CONTEXT: quantity cannot be assigned to the main item"


@dataclass(frozen=True)
class PassageScopeDecision:
    passage_id: str
    scope_match: ScopeMatch
    reason: str
    decided_by: str

    @property
    def needs_review(self) -> bool:
        return self.scope_match == ScopeMatch.AGENT


@dataclass(frozen=True)
class ScopeDecision:
    scope_match: ScopeMatch
    reason: str
    needs_scope_resolution: bool = False
    passage_scopes: tuple[PassageScopeDecision, ...] = ()

    def for_passage(self, passage_id: str) -> PassageScopeDecision:
        """A source mismatch cannot be undone by a stored passage placement."""
        if self.scope_match != ScopeMatch.MISMATCH:
            for placement in self.passage_scopes:
                if placement.passage_id == passage_id:
                    return placement
        return PassageScopeDecision(passage_id, self.scope_match, self.reason, "CODE")


def load_market_rules(path: Path) -> MarketRules | None:
    """Load server-owned data; absence is reported conservatively by inference."""
    if not path.exists():
        return None
    value: JsonValue = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Scope market data must be an object")
    arrays: dict[str, frozenset[str]] = {}
    for key in ("country_tlds", "generic_cctlds"):
        entries = value.get(key)
        if not isinstance(entries, list) or not all(isinstance(item, str) for item in entries):
            raise ValueError("Scope market data must contain string arrays")
        if any(len(str(item)) != 2 or not str(item).isascii() or not str(item).isalpha()
               or not str(item).islower() for item in entries):
            raise ValueError("Market codes must be lowercase two-letter codes")
        arrays[key] = frozenset(str(item) for item in entries)
    return MarketRules(arrays["country_tlds"], arrays["generic_cctlds"])


def _market(uri: str, rules: MarketRules | None) -> tuple[str | None, bool]:
    try:
        parsed = urlsplit(uri)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None, False
        host = parsed.hostname.rstrip(".").lower()
    except ValueError:
        return None, False
    tld = host.rsplit(".", 1)[-1]
    if len(tld) != 2 or not tld.isascii() or not tld.isalpha():
        return None, False
    if rules is None:
        return None, True
    if tld not in rules.country_tlds or tld in rules.generic_cctlds:
        return None, False
    return ("GB" if tld == "uk" else tld.upper()), False


def _passages(source: Record) -> list[Record]:
    value = source.get("passages", [])
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError("Source passages must be objects")
    return value


def _placements(source: Record, passages: list[Record]) -> tuple[PassageScopeDecision, ...]:
    rows = source.get("passage_scopes", [])
    if not isinstance(rows, list):
        raise ValueError("Passage scopes must be an array")
    ids = {item.get("id", item.get("passage_id")) for item in passages}
    version = source.get("source_version_id")
    result: dict[str, PassageScopeDecision] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Passage scopes must be objects")
        passage_id = row.get("passage_id")
        if not isinstance(passage_id, str) or passage_id not in ids:
            continue
        if version is None or row.get("source_version_id") != version:
            continue
        placement = PassageScopeDecision(passage_id, ScopeMatch(str(row["scope_match"])),
                                         str(row.get("reason") or "Stored passage scope"),
                                         str(row.get("decided_by") or "CODE"))
        if passage_id in result and result[passage_id] != placement:
            raise ValueError("Conflicting stored passage scopes")
        result[passage_id] = placement
    return tuple(result[key] for key in sorted(result))


def _sizes(texts: Sequence[str]) -> list[dict[str, JsonValue]]:
    # Tolerance is not transitive. Start from the smallest value in each unit
    # so a middle value cannot merge two disagreeing extremes by arriving first.
    candidates = sorted(
        (size for text in texts for size in normalize.volumes_in(text)),
        key=lambda size: (str(size["unit"]), float(str(size["value"]))),
    )
    sizes: list[dict[str, JsonValue]] = []
    for size in candidates:
        if not any(compare.same_volume(size, other) for other in sizes):
            sizes.append(size)
    return sizes


def infer_scope(source: Record, product: Record, *, market_rules: MarketRules | None = None) -> ScopeDecision:
    """Accept a stored source plus its passages/current passage_scopes.

    Market rules are versioned JSON data. Metadata uses snapshot ``scope`` or
    stored ``scope_json``; product uses id/product_id, variant and market.
    Passage placements are consumed by ``decision.for_passage(id)`` in policy.
    No database or network access; the caller supplies stored evidence rows.
    Optional market_rules is server-controlled configuration, never source text.
    Missing market data keeps a possible ccTLD UNKNOWN rather than guessing.
    """
    passages = _passages(source)
    placements = _placements(source, passages)

    def decision(match: ScopeMatch, reason: str, pending: bool = False) -> ScopeDecision:
        return ScopeDecision(match, reason, pending, placements)

    scope = source.get("scope")
    if scope is None:
        raw = source.get("scope_json")
        scope = json.loads(raw) if isinstance(raw, str) else {}
    if not isinstance(scope, dict):
        raise ValueError("Source scope must be an object")
    multi_variant = str(scope.get("variant") or "").casefold() == "multi"
    product_id = product.get("id", product.get("product_id"))
    if source.get("product_id") and product_id and source["product_id"] != product_id:
        return decision(ScopeMatch.MISMATCH, "Source belongs to another product")
    for key in ("product", "variant", "market", "version"):
        if key == "variant" and multi_variant:
            continue  # Dataset contract: MULTI requests passage-level placement, not a variant identity.
        expected = product_id if key == "product" else product.get(key)
        actual = scope.get(key)
        if actual and expected and str(actual).casefold() != str(expected).casefold():
            return decision(ScopeMatch.MISMATCH, f"Explicit {key} scope differs from case")
    if not multi_variant and all(scope.get(key) for key in ("product", "variant", "market")):
        return decision(ScopeMatch.MATCH, "Explicit source scope matches case")
    if source.get("kind") in {SourceKind.LISTING, SourceKind.PACKAGING_IMAGE,
                              SourceKind.NOTIFICATION_DOC, SourceKind.SELLER_UPLOAD,
                              SourceKind.REGISTRY_RECORD} and not multi_variant:
        return decision(ScopeMatch.MATCH, "Product-owned evidence is in scope")
    if source.get("kind") not in {SourceKind.BRAND_PAGE, SourceKind.WEB_PAGE} and not multi_variant:
        return decision(ScopeMatch.UNKNOWN, "Source kind does not support scope inference", True)
    if not scope.get("market"):
        rules = market_rules
        if rules is None:
            rules = load_market_rules(Path(__file__).parents[1] / "data/scope_markets.json")
        market, missing_data = _market(str(source.get("uri") or ""), rules)
        if missing_data:
            return decision(ScopeMatch.UNKNOWN, "Market inference data is unavailable", True)
        expected_market = str(product.get("market") or "").upper()
        if expected_market == "UK":
            expected_market = "GB"
        if market and not expected_market:
            return decision(ScopeMatch.UNKNOWN, "Case market is absent", True)
        if market and expected_market and market != expected_market:
            return decision(ScopeMatch.MISMATCH, "Country-code domain differs from case market")
    if scope.get("variant") and not multi_variant:
        return decision(ScopeMatch.MATCH, "Explicit variant scope matches case")
    texts = [str(item.get("text") or "") for item in passages]
    if isinstance(source.get("text"), str):
        texts.append(str(source["text"]))
    rules = load_scope_text_rules()
    if rules is None and any(normalize.volumes_in(text) for text in texts):
        return decision(ScopeMatch.UNKNOWN, "Scope text rules are unavailable", True)
    scoped_sizes = [item for text in texts for item in _volume_roles(text,rules)] if rules else []
    if any(role == ScopeMatch.UNKNOWN for _,_,role in scoped_sizes):
        return decision(ScopeMatch.UNKNOWN, "Ambiguous promotional quantities require passage-level scope", True)
    if scoped_sizes and all(role == ScopeMatch.MISMATCH for _,_,role in scoped_sizes):
        return decision(ScopeMatch.UNKNOWN, "Only gift quantities are stated; main size needs confirmation", True)
    sizes = _sizes([raw for raw,_,role in scoped_sizes if role == ScopeMatch.MATCH])
    if len(sizes) > 1 or multi_variant:
        by_id = {item.passage_id: item for item in placements}
        unresolved = not passages or any(
            str(item.get("id", item.get("passage_id", ""))) not in by_id or
            by_id[str(item.get("id", item.get("passage_id", "")))].scope_match == ScopeMatch.UNKNOWN
            for item in passages
        )
        return decision(ScopeMatch.UNKNOWN, "Several sizes require passage-level scope", unresolved)
    if sizes:
        target = product.get("volume")
        targets = [target] if isinstance(target, dict) else _sizes([str(product.get("variant") or "")])
        if len(targets) != 1:
            return decision(ScopeMatch.UNKNOWN, "Case variant has no unambiguous size", True)
        if not compare.same_volume(sizes[0], targets[0]):
            return decision(ScopeMatch.MISMATCH, "Page names another size")
        return decision(ScopeMatch.MATCH, "Page size matches case variant")
    return decision(ScopeMatch.MATCH, "Page applies at product level")


def _copy_text(passage: Passage) -> str:
    text = passage if isinstance(passage, str) else passage.get("text", "")
    if not isinstance(text, str):
        raise ValueError("Passage text must be a string")
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def _shingles(text: str) -> set[str]:
    return {text[index:index + 5] for index in range(len(text) - 4)}


def listing_copies_reference(listing_passages: Sequence[Passage],
                             reference: Record | Sequence[Passage]) -> bool:
    """R7c: caller supplies only passages stating ONE field from ONE reference.

    True means policy should reuse that reference's family and record R7c in
    explain. This helper never mutates observations or assigns a public verdict.
    """
    references: Sequence[Passage] = _passages(reference) if isinstance(reference, Mapping) else reference
    if not listing_passages or not references:
        return False
    for key in ("source_id", "source_version_id"):
        identities = {item[key] for item in references if isinstance(item, Mapping) and item.get(key)}
        if len(identities) > 1:
            return False
    reference_sets = [_shingles(text) for item in references if len(text := _copy_text(item)) >= 30]
    for passage in listing_passages:
        text = _copy_text(passage)
        if len(text) < 30:
            return False
        shingles = _shingles(text)
        if not any(len(shingles & other) / len(shingles | other) >= 0.8 for other in reference_sets):
            return False
    return True
