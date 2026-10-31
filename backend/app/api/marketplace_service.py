"""Operator marketplace scans outside the passport case, with bounded extraction."""
from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import cast
from uuid import uuid4

from fastapi import HTTPException
from pydantic import JsonValue

from app import config, db, seed, store
from app.api import read
from app.api.dependencies import RequestActor
from app.api.s4_contracts import (
    BuyerMarketplaceResponse, ExpertMarketplaceResponse, MarketplaceFieldTally,
    MarketplaceScanResponse, MarketplaceSellerFinding, MarketplaceValueTally,
)
from app.budget import Budget, BudgetExceeded
from app.context import RunContext
from app.llm.client import LLMError
from app.models import Citation, PUBLIC_FIELDS, Role, SourceKind, ScopeMatch
from app.pipeline import compare, extract, marketplace, policy, publish
from app.pipeline.run import observe_source
from app.trace import TraceWriter


@dataclass
class SellerEvidence:
    listing: marketplace.SellerListing
    shop: str
    citations: dict[str, Citation]


def _seller(path: Path, product_id: str, ctx: RunContext) -> SellerEvidence:
    snapshot = seed.read_object(path)
    if (snapshot.get("product_id") != product_id or snapshot.get("kind") != "LISTING"
            or snapshot.get("visibility") != "PUBLIC" or snapshot.get("dataset_origin") not in {"REAL", "SYNTHETIC"}):
        raise ValueError("Marketplace snapshot must be a public listing for this product")
    ctx.budget.take_tool("marketplace:ingest")
    ref = store.add_source_version(snapshot, case_id=None, origin=str(snapshot["dataset_origin"]))
    passages = {str(p["id"]): p for p in store.passages(ref.id)}
    source = read.one("SELECT s.*,v.id AS source_version_id,v.version,v.scope_json FROM sources s "
                      "JOIN source_versions v ON v.source_id=s.id WHERE v.id=?", (ref.id,))
    observations = observe_source(source, ctx.product, ctx, extract.extract_source_version)
    excluded = [o for o in observations if o.field_key and (o.scope_match != ScopeMatch.MATCH or o.mapped_by == "model")]
    if excluded:
        ctx.trace.step("marketplace:seller_skipped", input_refs=[ref.id], detail={"scope": "FIELD", "reason": "UNCONFIRMED_SCOPE_OR_MAPPING", "fields": sorted({o.field_key for o in excluded})})
    values: dict[str, JsonValue] = {}
    citations: dict[str, Citation] = {}
    for field in PUBLIC_FIELDS:
        claims = [c for c in observations if c.field_key == field and compare.has_value(field, c.normalized) and c.quote
                  and c.scope_match == ScopeMatch.MATCH and c.mapped_by != "model"
                  and c.readability != "UNREADABLE" and c.source_version_id == ref.id and c.passage_id in passages
                  and publish.quote_text(c.quote) in publish.quote_text(str(passages[c.passage_id]["text"]))]
        if not claims:
            continue
        if any(c.normalized != claims[0].normalized for c in claims[1:]):
            ctx.trace.step("marketplace:seller_skipped", input_refs=[ref.id], detail={"field_key": field, "reason": "MULTIPLE_VALUES", "scope": "FIELD"})
            continue
        claim = claims[0]
        values[field] = claim.normalized
        citations[field] = Citation(passage_id=claim.passage_id, source_kind=SourceKind.LISTING,
            source_version=ref.version, locator=str(passages[claim.passage_id]["locator"]), excerpt=claim.quote)
    return SellerEvidence(marketplace.SellerListing(ref.source_id,
        "\n".join(str(p["text"]) for p in passages.values()), values), str(snapshot.get("shop_name") or ref.source_id), citations)


def scan(product_id: str, actor: RequestActor) -> MarketplaceScanResponse:
    if actor.role != Role.OPERATOR:
        raise HTTPException(403, "Operator role required")
    product = read.one("SELECT * FROM products WHERE id=?", (product_id,))
    product["web"] = db.loads(str(product.get("web_json") or "{}"))
    case = read.one("SELECT * FROM cases WHERE product_id=?", (product_id,))
    root = (config.settings.fixtures_dir / "marketplace").resolve()
    folder = (root / product_id).resolve()
    if folder.parent != root or not folder.is_dir():
        raise HTTPException(404, "Marketplace snapshots unavailable")
    paths = sorted(folder.glob("*.json"))
    if not paths:
        raise HTTPException(404, "Marketplace snapshots unavailable")
    budget = Budget.from_settings()
    mode = "replay" if config.settings.replay_freeze and config.settings.llm_mode != "fallback" else config.settings.llm_mode
    scan_id, now = "marketplace_" + uuid4().hex, db.now_iso()
    with db.transaction() as connection:
        connection.execute("INSERT INTO runs(id,case_id,case_revision,status,policy_version,llm_mode,budget_json,created_at,started_at) "
                           "VALUES(?,NULL,?,'RUNNING',?,?,?,?,?)",
                           (scan_id, case["revision"], policy.POLICY_VERSION, "LIVE" if mode == "record" else mode.upper(), db.dumps(budget.usage()), now, now))
    trace = TraceWriter(scan_id)
    ctx = RunContext(scan_id, str(case["id"]), str(case["tenant_id"]), int(str(case["revision"])), product, mode, budget, trace)
    trace.step("pin_revision", input_refs=[product_id], detail={"product_id": product_id, "mode": mode.upper(), "purpose": "MARKETPLACE_SCAN", "case_revision": case["revision"]})
    try:
        return _execute_scan(product_id, paths, ctx)
    except (ValueError, RuntimeError, sqlite3.Error) as failure:
        with db.transaction() as connection:
            connection.execute("UPDATE runs SET status='FAILED',stop_reason='MARKETPLACE_ERROR',error=?,usage_json=?,finished_at=? WHERE id=?",
                               (type(failure).__name__, db.dumps(budget.usage()), db.now_iso(), scan_id))
        trace.step("run:stop", error=type(failure).__name__, detail={"stop_reason": "MARKETPLACE_ERROR"})
        raise HTTPException(500, "Marketplace scan could not finish") from failure


def _execute_scan(product_id: str, paths: list[Path], ctx: RunContext) -> MarketplaceScanResponse:
    scan_id, budget, trace, mode = ctx.run_id, ctx.budget, ctx.trace, ctx.mode
    sellers: list[SellerEvidence] = []
    skipped, published, stop = 0, 0, None
    for path in paths:
        try:
            evidence = _seller(path, product_id, ctx)
            if any(item.listing.seller_id == evidence.listing.seller_id for item in sellers):
                raise ValueError("Duplicate seller source")
            sellers.append(evidence)
        except BudgetExceeded as failure:
            stop = failure.reason
            skipped += len(paths) - len(sellers) - skipped
            trace.step("marketplace:seller_skipped", input_refs=[path.name], detail={"reason": stop})
            break
        except LLMError as failure:
            skipped += 1
            trace.step("marketplace:seller_skipped", input_refs=[path.name], detail={"reason": failure.code})
        except (OSError, ValueError, KeyError, TypeError) as failure:
            skipped += 1
            trace.step("marketplace:seller_skipped", input_refs=[path.name], detail={"reason": type(failure).__name__})
    result = marketplace.consensus([item.listing for item in sellers])
    clusters = {seller: cluster.cluster_id for cluster in result.clusters for seller in cluster.seller_ids}
    fields = {item.field_key: item for item in result.fields}
    publications: list[publish.MarketplacePublication] = []
    for seller in sellers:
        for field, citation in seller.citations.items():
            value = cast(dict[str, JsonValue], seller.listing.values[field])
            publications.append(publish.MarketplacePublication(product_id, scan_id, seller.listing.seller_id, seller.shop,
                field, value, policy.display_value(field, value), clusters[seller.listing.seller_id],
                seller.listing.seller_id in fields[field].outlier_seller_ids, citation))
    publication_passed = publish.marketplace_gate(publications)
    if publication_passed:
        published = len(publications)
        trace.step("publish", detail={"marketplace_findings": published, "passport_fields": 0})
    else:
        stop = stop or "MARKETPLACE_CITATION_BLOCKED"
        trace.step("publish:blocked", detail={"reason": "MARKETPLACE_CITATION_BLOCKED", "stop_reason": stop})
    tallies = [MarketplaceFieldTally(field_key=field.field_key, independent_clusters=field.independent_clusters,
        values=[MarketplaceValueTally(value=cast(dict[str, JsonValue], vote.value),
                display=policy.display_value(field.field_key, vote.value), independent_clusters=len(vote.cluster_ids)) for vote in field.values],
        majority=cast(dict[str, JsonValue] | None, field.majority)) for field in result.fields]
    if not publication_passed:
        tallies = []
    stop = stop or budget.stop_reason or ("SELLERS_SKIPPED" if skipped else None)
    trace.step("publish", detail={"product_id": product_id, "marketplace_fields": [field.model_dump(mode="json") for field in tallies]})
    usage = budget.usage()
    with db.transaction() as connection:
        connection.execute("UPDATE runs SET status=?,stop_reason=?,usage_json=?,finished_at=? WHERE id=?",
            ("PARTIAL" if stop else "COMPLETED", stop, db.dumps(usage), db.now_iso(), scan_id))
    trace.step("run:stop", detail={"stop_reason": stop, "budget": usage})
    return MarketplaceScanResponse(product_id=product_id, scan_id=scan_id, sellers_processed=len(sellers),
        sellers_skipped=skipped, findings=published, llm_mode="LIVE" if mode == "record" else mode.upper(), stop_reason=stop)


def view(product_id: str, actor: RequestActor) -> BuyerMarketplaceResponse | ExpertMarketplaceResponse:
    read.one("SELECT id FROM products WHERE id=?", (product_id,))
    scan_id: str | None = None
    fields: list[MarketplaceFieldTally] = []
    for row in read.rows("SELECT run_id,detail FROM trace_steps WHERE step='publish' ORDER BY created_at DESC,id DESC"):
        detail = db.loads(str(row["detail"]))
        if isinstance(detail, dict) and detail.get("product_id") == product_id and "marketplace_fields" in detail:
            scan_id = str(row["run_id"])
            fields = [MarketplaceFieldTally.model_validate(value) for value in detail["marketplace_fields"]]
            break
    if actor.role not in {Role.REVIEWER, Role.OPERATOR}:
        return BuyerMarketplaceResponse(product_id=product_id, scan_id=scan_id, fields=fields)
    findings = [MarketplaceSellerFinding(seller_source_id=row["seller_source_id"], shop=row["shop"],
        field_key=row["field_key"], value=db.loads(str(row["value_json"])), display=row["display"], cluster=row["cluster"],
        outlier=bool(row["outlier"]), citation=Citation.model_validate_json(str(row["citation_json"])), dataset_origin=row["dataset_origin"])
        for row in read.rows("SELECT f.*,s.dataset_origin FROM marketplace_findings f JOIN sources s ON s.id=f.seller_source_id "
                            "WHERE f.product_id=? AND f.scan_id=? ORDER BY f.field_key,f.seller_source_id", (product_id, scan_id))]
    return ExpertMarketplaceResponse(product_id=product_id, scan_id=scan_id, fields=fields, findings=findings)
