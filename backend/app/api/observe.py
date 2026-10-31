"""S1 persisted execution counts and the in-memory buyer read counter."""
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import JsonValue

from app import chain, db
from app.api import read
from app.api.contracts import EventCounts, MetricsResponse, ModelCallCounts
from app.api.dependencies import OperatorActor, RunActor
from app.models import Citation, ContractModel, DependsOn
from app.retrieval import search as retrieval

router = APIRouter()


@router.get("/internal/metrics", response_model=MetricsResponse)
def metrics(actor: OperatorActor) -> MetricsResponse:
    outcomes = {str(row["outcome"]): int(row["n"]) for row in read.rows("SELECT outcome,COUNT(*) AS n FROM events GROUP BY outcome")}
    runs = [read.run_response(row) for row in read.rows("SELECT * FROM runs")]
    return MetricsResponse(events=EventCounts(**{key: outcomes.get(key,0) for key in EventCounts.model_fields}),
        runs=len(runs),jobs=read.one("SELECT COUNT(*) AS n FROM jobs")["n"],
        model_calls=ModelCallCounts(live=sum(r.usage.model_calls for r in runs if r.llm_mode == "LIVE"),
                                   replayed=sum(r.usage.model_calls for r in runs if r.llm_mode == "REPLAY"),avoided=0),
        passport_reads=read.passport_reads())


class GraphSource(ContractModel):
    source_id: str
    source_version_id: str
    version: int
    kind: str
    status: str
    is_current: bool
    dataset_origin: str


class GraphField(ContractModel):
    result_id: str
    field_key: str
    freshness: str


class GraphEdge(ContractModel):
    source_version_id: str
    result_id: str
    relation: Literal["DEPENDS_ON", "CITES"]


class GraphResponse(ContractModel):
    case_id: str
    sources: list[GraphSource]
    fields: list[GraphField]
    edges: list[GraphEdge]


class SearchResponse(ContractModel):
    hits: list[dict[str, JsonValue]]
    stages: dict[str, list[dict[str, JsonValue]]]


@router.get("/cases/{case_id}/chain", response_model=chain.ChainVerification)
def case_chain(case_id: str, actor: RunActor) -> chain.ChainVerification:
    read.one("SELECT id FROM cases WHERE id=?", (case_id,))
    return chain.verify(case_id)


@router.get("/cases/{case_id}/graph", response_model=GraphResponse)
def case_graph(case_id: str, actor: RunActor) -> GraphResponse:
    read.one("SELECT id FROM cases WHERE id=?", (case_id,))
    sources = [GraphSource.model_validate(row) for row in read.rows(
        "SELECT s.id AS source_id,v.id AS source_version_id,v.version,s.kind,s.status,"
        "v.is_current,s.dataset_origin FROM sources s JOIN source_versions v ON v.source_id=s.id "
        "WHERE s.case_id=? ORDER BY s.id,v.version", (case_id,))]
    allowed = {source.source_version_id for source in sources}
    passage_versions = {str(row["id"]): str(row["source_version_id"]) for row in read.rows(
        "SELECT p.id,p.source_version_id FROM passages p JOIN source_versions v ON v.id=p.source_version_id "
        "JOIN sources s ON s.id=v.source_id WHERE s.case_id=?", (case_id,))}
    fields: list[GraphField] = []
    edges: list[GraphEdge] = []
    for row in read.rows("SELECT * FROM field_results WHERE case_id=? AND superseded_by IS NULL ORDER BY field_key,id", (case_id,)):
        fields.append(GraphField(result_id=row["id"], field_key=row["field_key"], freshness=row["freshness"]))
        dependencies = [DependsOn.model_validate(value) for value in db.loads(str(row["depends_on_json"]))]
        citations = [Citation.model_validate(value) for value in db.loads(str(row["citations_json"]))]
        for relation, versions in (("DEPENDS_ON", {d.source_version_id for d in dependencies}),
                                   ("CITES", {passage_versions[c.passage_id] for c in citations
                                              if c.passage_id in passage_versions})):
            for version in sorted(versions & allowed):
                edges.append(GraphEdge(source_version_id=version, result_id=row["id"], relation=relation))
    return GraphResponse(case_id=case_id, sources=sources, fields=fields, edges=edges)


@router.get("/cases/{case_id}/search", response_model=SearchResponse)
def case_search(case_id: str, actor: RunActor,
                q: Annotated[str, Query(min_length=1, pattern=r"\S")],
                mode: Literal["auto", "bm25", "hybrid"] = "auto") -> SearchResponse:
    read.one("SELECT id FROM cases WHERE id=?", (case_id,))
    allowed = [str(row["id"]) for row in read.rows(
        "SELECT v.id FROM source_versions v JOIN sources s ON s.id=v.source_id "
        "WHERE s.case_id=? AND s.status='ACTIVE' AND v.is_current=1 ORDER BY v.id", (case_id,))]
    result = retrieval.search(case_id, q, mode=mode, allowed_sv_ids=allowed)
    return SearchResponse(hits=result.hits, stages=result.stages)
