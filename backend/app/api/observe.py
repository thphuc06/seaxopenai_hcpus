"""Read-only observability and expert evidence routes."""
from typing import Annotated, Literal
from fastapi import APIRouter, Query
from pydantic import JsonValue
from app import chain, db
from app.api import read, glassbox
from app.api.contracts import EventCounts, MetricsResponse, ModelCallCounts
from app.api.dependencies import Actor, OperatorActor, RunActor, not_implemented
from app.api.glassbox_contracts import (BuyerExplanation, ExpertExplanation, ChainResponse,
    GraphResponse, GraphNode, GraphEdge, ObservabilityResponse, OtelResponse, SearchResponse)
from app.models import Citation, DependsOn
from app.retrieval import search as retrieval

router = APIRouter()


@router.get("/internal/eval/metrics", response_model=dict[str, JsonValue])
def evaluation_metrics(actor: RunActor) -> dict[str, JsonValue]:
    not_implemented()


@router.get("/products/{product_id}/fields/{field_key}/explain", response_model=BuyerExplanation | ExpertExplanation)
def explain(product_id: str, field_key: str, actor: Actor) -> BuyerExplanation | ExpertExplanation:
    return glassbox.explain(product_id, field_key, actor.role)


@router.get("/internal/observability", response_model=ObservabilityResponse)
def observability(actor: RunActor) -> ObservabilityResponse:
    return glassbox.observability()


@router.get("/cases/{case_id}/chain", response_model=ChainResponse)
def case_chain(case_id: str, actor: RunActor) -> ChainResponse:
    read.one("SELECT id FROM cases WHERE id=?", (case_id,))
    checked = chain.verify(case_id)
    broken = None
    if checked.broken_at is not None:
        ordered = read.rows("SELECT id FROM field_results WHERE case_id=? ORDER BY chain_seq IS NULL,chain_seq,created_at,id", (case_id,))
        broken = next(i for i, row in enumerate(ordered, 1) if row["id"] == checked.broken_at)
    return ChainResponse(valid=checked.valid, rows=checked.rows, head=checked.head, broken_at=broken)


@router.get("/cases/{case_id}/graph", response_model=GraphResponse)
def case_graph(case_id: str, actor: RunActor) -> GraphResponse:
    read.one("SELECT id FROM cases WHERE id=?", (case_id,))
    sources = read.rows("SELECT v.id,s.kind,s.status,v.is_current,s.dataset_origin FROM sources s JOIN source_versions v ON v.source_id=s.id WHERE s.case_id=? ORDER BY v.id", (case_id,))
    nodes = [GraphNode(id=str(s["id"]), kind="source", label=("MOCK registry" if s["kind"] == "REGISTRY_RECORD" else str(s["kind"]))+" · "+str(s["dataset_origin"]), status=str(s["status"]) if s["is_current"] else "SUPERSEDED") for s in sources]
    allowed = {s["id"] for s in sources}
    passage_versions = {str(r["id"]): str(r["source_version_id"]) for r in read.rows("SELECT p.id,p.source_version_id FROM passages p JOIN source_versions v ON v.id=p.source_version_id JOIN sources s ON s.id=v.source_id WHERE s.case_id=?", (case_id,))}
    edges: list[GraphEdge] = []
    for row in read.rows("SELECT * FROM field_results WHERE case_id=? AND superseded_by IS NULL ORDER BY field_key,id", (case_id,)):
        nodes.append(GraphNode(id=str(row["id"]), kind="field", label=str(row["field_key"]), status=str(row["freshness"])))
        dependencies = [DependsOn.model_validate(v) for v in db.loads(str(row["depends_on_json"]))]
        citations = [Citation.model_validate(v) for v in db.loads(str(row["citations_json"]))]
        for relation, versions in (("depends_on", {d.source_version_id for d in dependencies}), ("cites", {passage_versions[c.passage_id] for c in citations if c.passage_id in passage_versions})):
            for version in sorted(versions & allowed):
                edges.append(GraphEdge(source=version, target=str(row["id"]), relation=relation))
    return GraphResponse(nodes=nodes, edges=edges)


@router.get("/cases/{case_id}/search", response_model=SearchResponse)
def case_search(case_id: str, actor: RunActor, q: Annotated[str, Query(min_length=1, pattern=r"\S")], mode: Literal["auto", "bm25", "hybrid"] = "auto") -> SearchResponse:
    read.one("SELECT id FROM cases WHERE id=?", (case_id,))
    allowed = [str(row["id"]) for row in read.rows("SELECT v.id FROM source_versions v JOIN sources s ON s.id=v.source_id WHERE s.case_id=? AND s.status='ACTIVE' AND v.is_current=1 ORDER BY v.id", (case_id,))]
    result = retrieval.search(case_id, q, mode=mode, allowed_sv_ids=allowed)
    return SearchResponse(hits=result.hits, stages=result.stages)


@router.get("/internal/runs/{run_id}/otel", response_model=OtelResponse)
def otel(run_id: str, actor: RunActor) -> OtelResponse:
    not_implemented()


@router.get("/internal/metrics", response_model=MetricsResponse)
def metrics(actor: OperatorActor) -> MetricsResponse:
    outcomes = {str(row["outcome"]): int(row["n"]) for row in read.rows("SELECT outcome,COUNT(*) AS n FROM events GROUP BY outcome")}
    runs = [read.run_response(row) for row in read.rows("SELECT * FROM runs")]
    return MetricsResponse(events=EventCounts(**{key: outcomes.get(key,0) for key in EventCounts.model_fields}), runs=len(runs), jobs=read.one("SELECT COUNT(*) AS n FROM jobs")["n"], model_calls=ModelCallCounts(live=sum(r.usage.model_calls for r in runs if r.llm_mode == "LIVE"), replayed=sum(r.usage.model_calls for r in runs if r.llm_mode == "REPLAY"), avoided=0), passport_reads=read.passport_reads())
