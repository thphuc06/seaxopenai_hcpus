"""S1 metrics contract; counters will be implemented in Stage B."""
from fastapi import APIRouter

from app.api import read
from app.api.contracts import EventCounts, MetricsResponse, ModelCallCounts
from app.api.dependencies import OperatorActor

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
