"""S1 run read contracts."""
from fastapi import APIRouter

from app.api.contracts import RunDetailResponse, RunResponse
from app.api.dependencies import RunActor, not_implemented

router = APIRouter()


@router.get("/internal/runs", response_model=list[RunResponse])
def runs(actor: RunActor) -> list[RunResponse]:
    not_implemented()


@router.get("/internal/runs/{run_id}", response_model=RunDetailResponse)
def run_detail(run_id: str, actor: RunActor) -> RunDetailResponse:
    not_implemented()
