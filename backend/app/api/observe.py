"""S1 persisted execution counts and the in-memory buyer read counter."""
from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app.api import read
from app.api.contracts import EventCounts, MetricsResponse, ModelCallCounts
from app.api.dependencies import Actor, OperatorActor, RunActor, not_implemented
from app.api.glassbox_contracts import (
    BuyerExplanation, ChainResponse, ExpertExplanation, GraphResponse,
    ObservabilityResponse, OtelResponse, SearchResponse,
)

router = APIRouter()


@router.get("/products/{product_id}/fields/{field_key}/explain",
            response_model=BuyerExplanation | ExpertExplanation)
def explain(product_id: str, field_key: str, actor: Actor) -> BuyerExplanation | ExpertExplanation:
    not_implemented()


@router.get("/internal/observability", response_model=ObservabilityResponse)
def observability(actor: RunActor) -> ObservabilityResponse:
    not_implemented()


@router.get("/cases/{case_id}/chain", response_model=ChainResponse)
def chain(case_id: str, actor: RunActor) -> ChainResponse:
    not_implemented()


@router.get("/cases/{case_id}/graph", response_model=GraphResponse)
def graph(case_id: str, actor: RunActor) -> GraphResponse:
    not_implemented()


@router.get("/cases/{case_id}/search", response_model=SearchResponse)
def search(case_id: str, actor: RunActor, q: Annotated[str, Query(min_length=1)],
           mode: Literal["auto", "bm25", "hybrid"] = "auto") -> SearchResponse:
    not_implemented()


@router.get("/internal/runs/{run_id}/otel", response_model=OtelResponse)
def otel(run_id: str, actor: RunActor) -> OtelResponse:
    not_implemented()


@router.get("/internal/metrics", response_model=MetricsResponse)
def metrics(actor: OperatorActor) -> MetricsResponse:
    outcomes = {str(row["outcome"]): int(row["n"]) for row in read.rows("SELECT outcome,COUNT(*) AS n FROM events GROUP BY outcome")}
    runs = [read.run_response(row) for row in read.rows("SELECT * FROM runs")]
    return MetricsResponse(events=EventCounts(**{key: outcomes.get(key,0) for key in EventCounts.model_fields}),
        runs=len(runs),jobs=read.one("SELECT COUNT(*) AS n FROM jobs")["n"],
        model_calls=ModelCallCounts(live=sum(r.usage.model_calls for r in runs if r.llm_mode == "LIVE"),
                                   replayed=sum(r.usage.model_calls for r in runs if r.llm_mode == "REPLAY"),avoided=0),
        passport_reads=read.passport_reads())
