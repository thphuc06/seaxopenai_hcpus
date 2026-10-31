"""S1 run read contracts."""
from fastapi import APIRouter

from app import db
from app.api import read
from app.api.contracts import RunDetailResponse, RunResponse, TraceStepResponse
from app.api.dependencies import RunActor

router = APIRouter()


@router.get("/internal/runs", response_model=list[RunResponse])
def runs(actor: RunActor) -> list[RunResponse]:
    return [read.run_response(row) for row in read.rows("SELECT * FROM runs WHERE case_id IS NOT NULL ORDER BY created_at DESC,id DESC LIMIT 100")]


@router.get("/internal/runs/{run_id}", response_model=RunDetailResponse)
def run_detail(run_id: str, actor: RunActor) -> RunDetailResponse:
    run = read.run_response(read.one("SELECT * FROM runs WHERE id=? AND case_id IS NOT NULL", (run_id,)))
    steps = []
    for row in read.rows("SELECT * FROM trace_steps WHERE run_id=? ORDER BY seq", (run_id,)):
        for field in ("input_refs", "output_refs", "detail"):
            row[field] = db.loads(str(row[field] or "null")) or ({} if field == "detail" else [])
        steps.append(TraceStepResponse.model_validate(row))
    return RunDetailResponse(run=run,steps=steps)
