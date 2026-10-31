"""S1 metrics contract; counters will be implemented in Stage B."""
from fastapi import APIRouter

from app.api.contracts import MetricsResponse
from app.api.dependencies import OperatorActor, not_implemented

router = APIRouter()


@router.get("/internal/metrics", response_model=MetricsResponse)
def metrics(actor: OperatorActor) -> MetricsResponse:
    not_implemented()
