"""S2 transport checkpoint; persistence and publication follow in Stage B."""
from fastapi import APIRouter

from app.api.contracts import (
    CaseHistoryResponse, EvidenceUploadRequest, ReviewQueueItem,
    ReviewRequest, ReviewResponse,
)
from app.api.dependencies import EvidenceActor, ReviewerActor, not_implemented
from app.models import AdmitResult

router = APIRouter()


@router.get("/review/queue", response_model=list[ReviewQueueItem])
def review_queue(actor: ReviewerActor) -> list[ReviewQueueItem]:
    not_implemented()


@router.post("/cases/{case_id}/reviews", response_model=ReviewResponse)
def submit_review(case_id: str, request: ReviewRequest, actor: ReviewerActor) -> ReviewResponse:
    not_implemented()


@router.get("/cases/{case_id}/history", response_model=CaseHistoryResponse)
def case_history(case_id: str, actor: ReviewerActor) -> CaseHistoryResponse:
    not_implemented()


@router.post("/cases/{case_id}/evidence", response_model=AdmitResult)
def upload_evidence(case_id: str, request: EvidenceUploadRequest, actor: EvidenceActor) -> AdmitResult:
    not_implemented()
