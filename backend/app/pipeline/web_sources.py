"""Code-checked discovery to stored evidence; policy and publication remain downstream."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
import sys
from typing import Literal
import unicodedata
from urllib.parse import unquote, urlsplit

import httpx
from openai import APIError
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from app import config, db, store
from app.agent import web_scout
from app.budget import BudgetExceeded
from app.connectors import websearch
from app.context import RunContext
from app.llm import client
from app.pipeline.fallback_extract import injection_spans

# P4 owns the only HTML parser/cleaner; backend Actions do not add repository root.
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from scripts.capture_page import CaptureError, clean_html


class WebRules(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    about: str = Field(alias="_about")
    query_templates: list[str]
    retailer_domains: list[str]
    comparison_terms: list[str]
    section_end_markers: list[str]


class WebOptions(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    enabled: bool = False
    brand_domains: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)


class DiscoveryReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal["outcome"] = "outcome"
    new_sv_ids: list[str]
    searches: list[dict[str, JsonValue]]
    stop_reason: str | None


@dataclass
class WebOutcome:
    new_sv_ids: list[str]
    searches: list[dict[str, JsonValue]]
    stop_reason: str | None


def discover(ctx: RunContext) -> WebOutcome:
    product, options = _authorized_product(ctx)
    if config.settings.web_search != "on" or not options.enabled:
        return WebOutcome([], [], None)
    cached = _receipt(ctx)
    if cached is not None:
        return WebOutcome(cached.new_sv_ids, cached.searches, cached.stop_reason)
    rules = WebRules.model_validate_json((Path(__file__).resolve().parents[1] / "data/web_search.json").read_text(encoding="utf-8"))
    official = [websearch.domain_name(value) for value in options.brand_domains]
    retailers = [websearch.domain_name(value) for value in rules.retailer_domains]
    domains = sorted(set(official + retailers))
    brand = str(product["brand"]).strip()
    if not brand or not domains:
        return _finish(ctx, WebOutcome([], [], "WEB_CONFIGURATION"))
    session = websearch.WebSession(ctx, domains, brand, str(product["market"]))
    outcome = WebOutcome([], [], None)
    try:
        planned = web_scout.queries(ctx, product, rules.query_templates)
    except client.LLMError as error:
        if error.code == "REPLAY_MISS" or ctx.mode == "replay" or config.settings.replay_freeze:
            return _finish(ctx, WebOutcome([], [], str(error)))
        outcome.stop_reason = "WEB_AGENT_ERROR"
        ctx.trace.step("agent:web_scout", actor="code", error=error.code,
                       detail={"mode": "FALLBACK", "action": "query_templates"})
        planned = [template.format(**product) for template in rules.query_templates]
    except BudgetExceeded as error:
        return _finish(ctx, WebOutcome([], [], error.reason))
    if not planned:
        return _finish(ctx, WebOutcome([], [], "WEB_NO_QUERIES"))
    for query in planned:
        if session.searches >= config.settings.web_max_searches or session.pages >= config.settings.web_max_pages:
            outcome.stop_reason = outcome.stop_reason or ("WEB_PAGE_LIMIT" if session.pages >= config.settings.web_max_pages else "WEB_SEARCH_LIMIT")
            break
        audit: dict[str, JsonValue] = {"kind": "query", "query": query, "mode": _audit_mode(ctx.mode), "results": [], "decisions": []}
        try:
            _authorized_product(ctx)
            results = session.search(query)
            audit["mode"] = _audit_mode(session.last_mode)
            audit["results"] = [item.model_dump(mode="json") for item in results]
            audit["decisions"] = [_candidate_decision(item, official, retailers) for item in results]
            try:
                selection = web_scout.select(ctx, product, results)
            except client.LLMError as error:
                if error.code == "REPLAY_MISS" or ctx.mode == "replay" or config.settings.replay_freeze:
                    raise
                outcome.stop_reason = outcome.stop_reason or "WEB_AGENT_ERROR"
                audit["selection_error"] = error.code
                selection = web_scout.select(replace(ctx, mode="fallback"), product, results)
            audit["selection_mode"] = selection.mode
            _process_pages(ctx, product, options, rules, official, retailers, session, results, selection, audit, outcome)
        except (client.LLMError, BudgetExceeded, websearch.WebError, httpx.HTTPError, APIError,
                OSError, ValidationError) as error:
            if isinstance(error, PermissionError):
                raise
            reason = _reason(error)
            audit["stop_reason"] = reason
            outcome.stop_reason = outcome.stop_reason or reason
            ctx.trace.step("web:skip", error=reason, detail={"reason": reason})
            if isinstance(error, BudgetExceeded) or (isinstance(error, client.LLMError) and error.code == "REPLAY_MISS"):
                outcome.searches.append(audit)
                _audit(ctx, query, audit)
                break
        outcome.searches.append(audit)
        _audit(ctx, query, audit)
    return _finish(ctx, outcome)


def _authorized_product(ctx: RunContext) -> tuple[dict[str, JsonValue], WebOptions]:
    with db.transaction() as connection:
        row = connection.execute("SELECT c.tenant_id,c.revision,p.id,p.name,p.brand,p.variant,p.market,p.web_json "
            "FROM cases c JOIN products p ON p.id=c.product_id WHERE c.id=?", (ctx.case_id,)).fetchone()
        run = connection.execute("SELECT case_id,case_revision FROM runs WHERE id=?", (ctx.run_id,)).fetchone()
    if (row is None or run is None or (row["tenant_id"], row["revision"], row["id"]) !=
            (ctx.tenant_id, ctx.case_revision, ctx.product.get("id")) or
            (run["case_id"], run["case_revision"]) != (ctx.case_id, ctx.case_revision)):
        raise PermissionError("ACCESS_DENIED_OR_SUPERSEDED_RUN")
    options = WebOptions.model_validate_json(str(row["web_json"] or "{}"))
    return {key: str(row[key] or "") for key in ("id", "name", "brand", "variant", "market")}, options


def _receipt(ctx: RunContext) -> DiscoveryReceipt | None:
    with db.transaction() as connection:
        row = connection.execute("SELECT results_json FROM web_searches WHERE id=? AND case_id=? AND run_id=?",
                                 (_audit_id(ctx, "outcome"), ctx.case_id, ctx.run_id)).fetchone()
    return DiscoveryReceipt.model_validate_json(row[0]) if row else None


def _audit_id(ctx: RunContext, value: str) -> str:
    return "web_" + sha256(json.dumps([ctx.case_id, ctx.run_id, value]).encode()).hexdigest()


def _audit_mode(mode: str) -> str:
    return "LIVE" if mode.lower() in {"live", "record"} else mode.upper()


def _audit(ctx: RunContext, query: str, payload: dict[str, JsonValue], *, terminal: bool = False) -> None:
    _authorized_product(ctx)
    with db.transaction() as connection:
        connection.execute("INSERT OR IGNORE INTO web_searches(id,case_id,run_id,query,provider,mode,results_json,credits,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)", (_audit_id(ctx, "outcome" if terminal else "query:" + query), ctx.case_id,
            ctx.run_id, query, config.settings.web_provider, str(payload.get("mode", _audit_mode(ctx.mode))), db.dumps(payload), None, db.now_iso()))


def _finish(ctx: RunContext, outcome: WebOutcome) -> WebOutcome:
    receipt = DiscoveryReceipt(new_sv_ids=outcome.new_sv_ids, searches=outcome.searches, stop_reason=outcome.stop_reason)
    _audit(ctx, "", receipt.model_dump(mode="json"), terminal=True)
    ctx.trace.step("web:stop", detail={"stop_reason": outcome.stop_reason, "mode": _audit_mode(ctx.mode),
                                    "new_sv_ids": outcome.new_sv_ids, "budget": ctx.budget.usage()})
    return outcome


def _reason(error: Exception) -> str:
    if isinstance(error, BudgetExceeded):
        return error.reason
    if isinstance(error, client.LLMError):
        return error.code
    if isinstance(error, websearch.WebError):
        return str(error)
    return "WEB_" + type(error).__name__.upper()


def _canonical(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).split())


def _contains_phrase(text: str, phrase: str) -> bool:
    return bool(phrase.strip()) and re.search(r"(?<!\w)" + re.escape(_canonical(phrase)) + r"(?!\w)",
                                            _canonical(text), re.IGNORECASE) is not None


def _comparison(text: str, terms: list[str]) -> bool:
    return any(_contains_phrase(unquote(text).replace("-", " ").replace("_", " "), term) for term in terms)


def _clean(page: websearch.Page, aliases: list[str], rules: WebRules) -> tuple[str, bool]:
    if page.content_type in {"text/html", "application/xhtml+xml"}:
        text = clean_html(page.text, section_end_markers=tuple(rules.section_end_markers))
    elif page.content_type == "text/plain":
        text = page.text
    else:
        raise websearch.WebError("UNSUPPORTED_CONTENT_TYPE")
    if _comparison(text.strip().splitlines()[0] if text.strip() else "", rules.comparison_terms):
        raise websearch.WebError("COMPARISON_PAGE")
    # Both captured HTML and an explicitly plain-text provider may contain a trailing related block.
    for marker in rules.section_end_markers:
        match = re.search(r"(?<!\w)" + re.escape(marker) + r"(?!\w)", text, re.IGNORECASE)
        if match:
            text = text[:match.start()]
    hits = [match.start() for alias in aliases if alias.strip() for match in
            [re.search(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", text, re.IGNORECASE)] if match]
    if hits:
        text = text[min(hits):]
    return text.strip(), bool(hits)


def _candidate_decision(item: websearch.Result, official: list[str], retailers: list[str]) -> dict[str, JsonValue]:
    try:
        url = websearch.normalized_url(item.url)
        category = "OFFICIAL" if websearch.matches_domain(url, official) else (
            "RETAILER" if websearch.matches_domain(url, retailers) else "LEAD")
        return {"url": item.url, "domain": urlsplit(url).hostname or "", "class": category, "score": None,
                "decision": "SKIP", "reason": "NOT_SELECTED"}
    except websearch.WebError:
        return {"url": item.url, "domain": "", "class": "LEAD", "score": None,
                "decision": "SKIP", "reason": "INVALID_URL"}


def _process_pages(ctx: RunContext, product: dict[str, JsonValue], options: WebOptions, rules: WebRules,
                   official: list[str], retailers: list[str], session: websearch.WebSession,
                   results: list[websearch.Result], selection: web_scout.ScoutResult,
                   audit: dict[str, JsonValue], outcome: WebOutcome) -> None:
    returned: dict[str, websearch.Result] = {}
    decisions = audit["decisions"]
    if not isinstance(decisions, list):
        raise ValueError("Discovery audit decisions must be a list")
    for item in results:
        try:
            url = websearch.normalized_url(item.url)
            returned[url] = item
        except websearch.WebError:
            ctx.trace.step("web:skip", detail={"reason": "INVALID_URL"})
    for proposal in selection.pages:
        if session.pages >= config.settings.web_max_pages:
            raise websearch.WebError("WEB_PAGE_LIMIT")
        entry = next((item for item in decisions if isinstance(item, dict) and item["url"] == proposal.url
                      and item["reason"] == "NOT_SELECTED"), None)
        if entry is None:
            entry = {"url": proposal.url, "domain": "", "class": "LEAD", "score": None,
                     "decision": "SKIP", "reason": "UNSELECTED"}
            decisions.append(entry)
        fetching = False
        try:
            url = websearch.normalized_url(proposal.url)
            entry["domain"] = urlsplit(url).hostname or ""
            item = returned.get(url)
            if item is None:
                raise websearch.WebError("URL_NOT_RETURNED")
            category = _candidate_decision(item, official, retailers)["class"]
            entry["class"] = category
            if category == "LEAD":
                raise websearch.WebError("UNCLASSIFIED_DOMAIN")
            if _comparison(item.title + " " + item.snippet + " " + urlsplit(url).path, rules.comparison_terms):
                raise websearch.WebError("COMPARISON_PAGE")
            if url in session.fetched_urls:
                raise websearch.WebError("REPEATED_PAGE")
            if selection.proposed_by_model and (not proposal.evidence_phrases or any(not p.strip() for p in proposal.evidence_phrases)):
                raise websearch.WebError("MISSING_EVIDENCE_PHRASE")
            _authorized_product(ctx)
            fetching = True
            page = session.fetch(url)
            entry["mode"] = _audit_mode(session.last_mode)
            _authorized_product(ctx)
            aliases = options.aliases or [str(product["name"])]
            cleaned, identity = _clean(page, aliases, rules)
            if selection.proposed_by_model and not all(any(_canonical(phrase) in _canonical(region)
                    for region in (item.title, item.snippet, cleaned)) for phrase in proposal.evidence_phrases):
                raise websearch.WebError("EVIDENCE_NOT_FOUND")
            if _comparison(cleaned.splitlines()[0] if cleaned else "", rules.comparison_terms):
                raise websearch.WebError("COMPARISON_PAGE")
            kind = "BRAND_PAGE" if category == "OFFICIAL" and identity else "WEB_PAGE"
            family_domain = next(domain for domain in sorted(official + retailers, key=len, reverse=True)
                                 if websearch.matches_domain(url, [domain]))
            source_version, created = _snapshot(ctx, product, url, page.fetched_at, cleaned, identity, kind, family_domain)
            entry.update(decision="SNAPSHOT" if created else "UNCHANGED", reason="IDENTITY_MATCH" if identity else "CONFIRM_ONLY",
                         source_version_id=source_version, identity_verified=identity,
                         injection_flagged=bool(injection_spans(cleaned)))
            if created:
                outcome.new_sv_ids.append(source_version)
            ctx.trace.step("web:snapshot", output_refs=[source_version], detail=entry)
        except (websearch.WebError, CaptureError, UnicodeError, httpx.HTTPError, OSError) as error:
            if isinstance(error, PermissionError):
                raise
            entry["reason"] = _reason(error)
            if fetching:
                outcome.stop_reason = outcome.stop_reason or str(entry["reason"])
            ctx.trace.step("web:skip", detail=entry, error=str(entry["reason"]))
            if isinstance(error, websearch.WebError) and str(error) == "WEB_PAGE_LIMIT":
                raise


def _snapshot(ctx: RunContext, product: dict[str, JsonValue], url: str, fetched_at: str, text: str,
              identity: bool, kind: str, family_domain: str) -> tuple[str, bool]:
    try:
        if datetime.fromisoformat(fetched_at).tzinfo is None:
            raise ValueError("timezone required")
    except ValueError:
        raise websearch.WebError("INVALID_CAPTURE_TIME") from None
    passages: list[dict[str, JsonValue]] = []
    pending: list[str] = []
    for line in text.splitlines():
        if line.strip():
            pending.append(line.strip())
            if len("\n".join(pending)) >= 30:
                passages.append({"locator": "web#p" + str(len(passages) + 1), "section": "web", "text": "\n".join(pending)})
                pending = []
    if pending and passages:
        passages[-1]["text"] = str(passages[-1]["text"]) + "\n" + "\n".join(pending)
    if not passages:
        raise websearch.WebError("NO_SUBSTANTIVE_PASSAGE")
    scope: dict[str, JsonValue] = {"identity_verified": identity, "confirm_only": not identity}
    source_id = "web_" + sha256(json.dumps([ctx.case_id, url]).encode()).hexdigest()
    ctx.budget.agent().gateway().check_active()
    _authorized_product(ctx)
    with db.transaction() as connection:
        current = connection.execute("SELECT s.status,s.kind,v.id,v.version,v.scope_json FROM sources s "
            "JOIN source_versions v ON v.source_id=s.id WHERE s.id=? AND v.is_current=1", (source_id,)).fetchone()
        if current:
            if current["status"] != "ACTIVE":
                raise websearch.WebError("SOURCE_INACTIVE")
            previous = [row[0] for row in connection.execute("SELECT text FROM passages WHERE source_version_id=? ORDER BY rowid", (current["id"],))]
            if (previous == [p["text"] for p in passages] and current["kind"] == kind
                    and json.loads(current["scope_json"]) == scope):
                return str(current["id"]), False
        version = int(current["version"]) + 1 if current else 1
    snapshot: dict[str, db.JSON] = {"source_id": source_id, "product_id": product["id"], "kind": kind,
        "version": version, "uri": url, "captured_at": fetched_at, "visibility": "PUBLIC",
        "dataset_origin": "REAL", "family": ("brand:" if kind == "BRAND_PAGE" else "web:") + family_domain,
        "scope": scope, "passages": passages}
    try:
        ctx.budget.agent().gateway().check_active()
        ref = store.add_source_version(snapshot, case_id=ctx.case_id, origin="REAL")
    except (sqlite3.IntegrityError, ValueError):
        raise websearch.WebError("SOURCE_VERSION_CHANGED") from None
    return ref.id, True
