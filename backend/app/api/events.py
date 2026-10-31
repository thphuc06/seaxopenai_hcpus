"""S1 event contracts; no admission side effects at the contract checkpoint."""
from fastapi import APIRouter

from app.api.contracts import EventCatalogItem, EventLogItem, ResetResponse
from app.api.dependencies import EventActor, OperatorActor, RunActor, not_implemented
from app.models import AdmitResult, EventEnvelope

router = APIRouter()


@router.post("/internal/events", response_model=AdmitResult)
def submit_event(event: EventEnvelope, actor: EventActor) -> AdmitResult:
    not_implemented()


@router.get("/internal/events/catalog", response_model=list[EventCatalogItem])
def event_catalog(actor: OperatorActor) -> list[EventCatalogItem]:
    not_implemented()


@router.get("/internal/events/log", response_model=list[EventLogItem])
def event_log(actor: RunActor) -> list[EventLogItem]:
    not_implemented()


@router.post("/internal/demo/fire/{name}", response_model=AdmitResult)
def fire_event(name: str, actor: OperatorActor) -> AdmitResult:
    not_implemented()


@router.post("/internal/demo/reset", response_model=ResetResponse)
def reset_demo(actor: OperatorActor) -> ResetResponse:
    not_implemented()
