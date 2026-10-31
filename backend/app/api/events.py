"""S1 admission, fixture dispatch and persisted event-log routes."""
from fastapi import APIRouter, BackgroundTasks, HTTPException
from app import config, db, seed, worker
from app.events.admit import admit
from app.api import read

from app.api.contracts import EventCatalogItem, EventLogItem, ResetResponse
from app.api.dependencies import EventActor, OperatorActor, RunActor, RequestActor
from app.models import AdmitResult, EventEnvelope

router = APIRouter()


@router.post("/internal/events", response_model=AdmitResult)
def submit_event(event: EventEnvelope, actor: EventActor, background_tasks: BackgroundTasks) -> AdmitResult:
    return dispatch(event, actor, background_tasks)


def dispatch(event: EventEnvelope, actor: RequestActor, background: BackgroundTasks) -> AdmitResult:
    result = admit(event, role=actor.role, actor_id=actor.actor_id)
    if result.job_id:
        if config.settings.worker_inline:
            worker.execute_job(result.job_id)
        else:
            background.add_task(worker.execute_job, result.job_id)
    return result


def fixture_event(name: str) -> tuple[EventEnvelope, str]:
    root = (config.settings.fixtures_dir / "events").resolve()
    path = (root / (name + ".json")).resolve()
    if path.parent != root or not path.is_file():
        raise HTTPException(404, "Event fixture not found")
    value = seed.read_object(path)
    expect = str(value.pop("expect", ""))
    return EventEnvelope.model_validate(value), expect


@router.get("/internal/events/catalog", response_model=list[EventCatalogItem])
def event_catalog(actor: OperatorActor) -> list[EventCatalogItem]:
    items = []
    for path in sorted((config.settings.fixtures_dir / "events").glob("*.json")):
        event, expect = fixture_event(path.stem)
        items.append(EventCatalogItem(name=path.stem,title=event.type.value,type=event.type,
                     product_id=str(event.payload.get("product_id", "")),resource=event.resource,expect=expect))
    return items


@router.get("/internal/events/log", response_model=list[EventLogItem])
def event_log(actor: RunActor) -> list[EventLogItem]:
    items = []
    for row in read.rows("SELECT * FROM events ORDER BY received_at DESC,id DESC LIMIT 100"):
        payload = db.loads(str(row["payload_json"]))
        if not isinstance(payload, dict):
            raise ValueError("Stored event payload is not an object")
        items.append(EventLogItem(event_id=row["event_id"],outcome=row["outcome"],reason=row["reason"],
            job_id=payload.get("job_id"),stale_fields=payload.get("stale_fields",[]),received_at=row["received_at"],run_id=row["run_id"]))
    return items


@router.post("/internal/demo/fire/{name}", response_model=AdmitResult)
def fire_event(name: str, actor: OperatorActor, background_tasks: BackgroundTasks) -> AdmitResult:
    event, _ = fixture_event(name)
    return dispatch(event,actor,background_tasks)


@router.post("/internal/demo/reset", response_model=ResetResponse)
def reset_demo(actor: OperatorActor) -> ResetResponse:
    seed.reset()
    read.passport_reads(reset=True)
    return ResetResponse(status="reset")
