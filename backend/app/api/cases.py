"""S2 transport checkpoint; persistence and publication follow in Stage B."""
import base64
import binascii
import hashlib
from threading import Lock
from fastapi import APIRouter, HTTPException, BackgroundTasks
from app import config, db
from app.api.events import dispatch
from app.api import read
from app.pipeline import publish, policy

from app.api.contracts import (
    CaseHistoryResponse, EvidenceUploadRequest, ReviewQueueItem,
    ReviewRequest, ReviewResponse, ResultVersionResponse, EvidenceRequestResponse, EventLogItem,
)
from app.api.dependencies import EvidenceActor, ReviewerActor
from app.models import AdmitResult, EventEnvelope

router = APIRouter()
_uploads = Lock()


@router.get("/review/queue", response_model=list[ReviewQueueItem])
def review_queue(actor: ReviewerActor) -> list[ReviewQueueItem]:
    return [ReviewQueueItem.model_validate(row) for row in read.rows(
        "SELECT t.id,t.case_id,t.field_key,t.result_id,c.revision AS case_revision,t.reason_code,r.verdict "
        "FROM review_tasks t JOIN field_results r ON r.id=t.result_id JOIN cases c ON c.id=t.case_id "
        "LEFT JOIN runs confirmed ON confirmed.id=r.confirmed_run_id "
        "WHERE t.status='OPEN' AND r.superseded_by IS NULL AND COALESCE(confirmed.case_revision,r.case_revision)=c.revision")]


@router.post("/cases/{case_id}/reviews", response_model=ReviewResponse)
def submit_review(case_id: str, request: ReviewRequest, actor: ReviewerActor) -> ReviewResponse:
    try:
        identity = publish.review(case_id,request.result_id,request.case_revision,request.decision,request.reason,
                                  request.override.model_dump(mode="json") if request.override else None,actor.actor_id)
    except publish.ReviewError as error:
        raise HTTPException(error.status,str(error)) from error
    return review_response(read.one("SELECT * FROM reviews WHERE id=?",(identity,)),request.case_revision)


def review_response(row: dict[str, db.JSON], current_revision: int) -> ReviewResponse:
    value = dict(row)
    value["override"] = db.loads(str(value.pop("override_json")))
    value["review_state"] = policy.review_freshness(int(value["case_revision"]),current_revision)
    return ReviewResponse.model_validate(value)


@router.get("/cases/{case_id}/history", response_model=CaseHistoryResponse)
def case_history(case_id: str, actor: ReviewerActor) -> CaseHistoryResponse:
    case = read.one("SELECT * FROM cases WHERE id=?",(case_id,))
    results = []
    for row in read.rows("SELECT * FROM field_results WHERE case_id=? ORDER BY result_version",(case_id,)):
        citations, _ = read.evidence(str(row["citations_json"]),actor.role)
        results.append(ResultVersionResponse(id=row["id"],case_id=case_id,result_version=row["result_version"],
            case_revision=row["case_revision"],created_at=row["created_at"],superseded_by=row["superseded_by"],
            field_key=row["field_key"],label=row["verdict"],public_text=row["public_text"],verdict=row["verdict"],
            conflict_locus=row["conflict_locus"],freshness=row["freshness"],review_state=row["review_state"],
            checked_at=row["confirmed_at"] or row["created_at"],citations=citations))
    events = []
    for row in read.rows("SELECT * FROM events WHERE COALESCE(json_extract(payload_json,'$.case_id'),json_extract(payload_json,'$.event.payload.case_id'))=?",(case_id,)):
        payload = db.loads(str(row["payload_json"]))
        events.append(EventLogItem(event_id=row["event_id"],outcome=row["outcome"],reason=row["reason"],
            job_id=payload.get("job_id"),stale_fields=payload.get("stale_fields",[]),received_at=row["received_at"],run_id=row["run_id"]))
    return CaseHistoryResponse(case_id=case_id,case_revision=case["revision"],results=results,events=events,
        reviews=[review_response(row,int(case["revision"])) for row in read.rows("SELECT * FROM reviews WHERE case_id=?",(case_id,))],
        requests=[EvidenceRequestResponse.model_validate(row) for row in read.rows("SELECT * FROM evidence_requests WHERE case_id=?",(case_id,))])


@router.post("/cases/{case_id}/evidence", response_model=AdmitResult)
def upload_evidence(case_id: str, request: EvidenceUploadRequest, actor: EvidenceActor, background_tasks: BackgroundTasks) -> AdmitResult:
    with _uploads:
        return _upload_evidence(case_id,request,actor,background_tasks)


def _upload_evidence(case_id: str, request: EvidenceUploadRequest, actor: EvidenceActor, background_tasks: BackgroundTasks) -> AdmitResult:
    case = read.one("SELECT c.*,p.variant,p.market FROM cases c JOIN products p ON p.id=c.product_id WHERE c.id=?",(case_id,))
    identity = hashlib.sha256((case_id+":"+actor.actor_id+":"+request.idempotency_key).encode("utf-8")).hexdigest()
    key = "upload:"+identity
    previous = read.rows("SELECT event_id FROM events WHERE idempotency_key=?",(key,))
    if previous:
        return AdmitResult(event_id=previous[0]["event_id"],outcome="DUPLICATE",reason="Idempotency key already recorded",job_id=None,stale_fields=[])
    directory = config.settings.fixtures_dir / "uploads"
    directory.mkdir(parents=True,exist_ok=True)
    path = directory / (identity+".json")
    text = request.content.text if request.content.kind == "TEXT" else ""
    if request.content.kind == "IMAGE":
        try:
            image = base64.b64decode(request.content.data_base64,validate=True)
        except (ValueError,binascii.Error) as error:
            raise HTTPException(422,"Invalid image encoding") from error
        png = request.content.media_type == "image/png"
        if not image.startswith(b"\x89PNG\r\n\x1a\n" if png else b"\xff\xd8\xff") or len(image) > 10_000_000:
            raise HTTPException(422,"Invalid image format or size")
        path.with_suffix(".png" if png else ".jpg").write_bytes(image)
    snapshot = {"source_id":"upload_"+identity,"product_id":case["product_id"],"version":1,
        "kind":"PACKAGING_IMAGE" if request.content.kind == "IMAGE" else "SELLER_UPLOAD",
        "visibility":"PRIVATE","family":"upload:"+actor.actor_id,"owner":actor.actor_id,
        "dataset_origin":case["dataset_origin"],"captured_at":db.now_iso(),"note":"Uploaded image awaiting extraction",
        "scope":{"product":case["product_id"],"variant":case["variant"],"market":case["market"]},
        "passages":[{"locator":"upload:1","section":"upload","text":text}]}
    path.write_text(db.dumps(snapshot),encoding="utf-8")
    event = EventEnvelope(event_id="upload_event_"+identity,idempotency_key=key,type="EVIDENCE_ADDED",
        schema_version="1",producer="seller-portal",resource={"kind":"SOURCE","id":snapshot["source_id"],"version":1},
        changed_fields=request.field_keys,payload={"case_id":case_id,"product_id":case["product_id"],"snapshot":"uploads/"+path.name},
        occurred_at=db.now_iso(),correlation_id=identity)
    return dispatch(event,actor,background_tasks)
