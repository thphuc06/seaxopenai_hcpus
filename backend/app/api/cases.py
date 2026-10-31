"""Revision-bound review, history and private evidence transport."""
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
from app.api.dependencies import EvidenceActor, ReviewerActor, OperatorActor, RunActor
from app.api.s4_contracts import WebAuditResponse, WebAuditQuery, WebAuditResult, WebAuditSnapshot, WebSnapshotPassage
from app.models import AdmitResult, EventEnvelope

router = APIRouter()
_uploads = Lock()


@router.post("/cases/{case_id}/web-search", response_model=AdmitResult)
def request_web_search(case_id: str, actor: OperatorActor, background_tasks: BackgroundTasks) -> AdmitResult:
    case = read.one("SELECT * FROM cases WHERE id=?", (case_id,))
    revision = int(str(case["revision"]))
    # Repeated clicks reuse the revision admitted by the previous click. A later
    # material event increments the revision and permits a new explicit request.
    previous = read.rows("SELECT event_id FROM events WHERE idempotency_key=? AND type='WEB_SEARCH_REQUESTED' AND outcome='ADMITTED'",
                         (f"web:{case_id}:{revision}",))
    if previous:
        return AdmitResult(event_id=str(previous[0]["event_id"]), outcome="DUPLICATE",
                           reason="Web search already requested for this revision", job_id=None, stale_fields=[])
    key = f"web:{case_id}:{revision + 1}"
    event = EventEnvelope(event_id=key, idempotency_key=key, type="WEB_SEARCH_REQUESTED", schema_version="1",
        producer="publisher-panel", resource={"kind": "CASE", "id": case_id, "version": revision + 1},
        changed_fields=[], payload={"case_id": case_id, "product_id": case["product_id"]},
        occurred_at=db.now_iso(), correlation_id=key)
    return dispatch(event, actor, background_tasks)


@router.get("/cases/{case_id}/web-search", response_model=WebAuditResponse)
def web_search_audit(case_id: str, actor: RunActor) -> WebAuditResponse:
    read.one("SELECT id FROM cases WHERE id=?", (case_id,))
    queries: list[WebAuditQuery] = []
    for row in read.rows("SELECT * FROM web_searches WHERE case_id=? ORDER BY created_at,id", (case_id,)):
        payload = db.loads(str(row["results_json"]))
        if isinstance(payload, dict) and payload.get("kind") == "outcome":
            continue
        items = payload.get("decisions") if isinstance(payload, dict) and payload.get("kind") == "query" else payload
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise HTTPException(409, "Web query audit is incomplete")
        results = [WebAuditResult.model_validate({key: item[key] for key in
            ("url", "domain", "class", "score", "decision", "reason") if key in item}) for item in items]
        queries.append(WebAuditQuery(id=row["id"], run_id=row["run_id"], query=row["query"], provider=row["provider"],
            mode=row["mode"], results=results, created_at=row["created_at"]))
    snapshots: list[WebAuditSnapshot] = []
    for row in read.rows("SELECT v.*,s.uri,s.kind,s.dataset_origin FROM source_versions v JOIN sources s ON s.id=v.source_id "
                         "WHERE s.case_id=? AND s.kind IN ('WEB_PAGE','BRAND_PAGE') ORDER BY v.captured_at,v.id", (case_id,)):
        scope = db.loads(str(row["scope_json"]))
        if row["kind"] != "WEB_PAGE" and "identity_verified" not in scope:
            continue
        if not row["uri"] or not row["captured_at"]:
            raise HTTPException(409, "Web snapshot metadata is incomplete")
        snapshots.append(WebAuditSnapshot(source_version_id=row["id"], url=row["uri"], sha256=row["sha256"],
            captured_at=row["captured_at"], dataset_origin=row["dataset_origin"], identity_verified=scope.get("identity_verified") is True,
            passages=[WebSnapshotPassage.model_validate(item) for item in read.rows(
                "SELECT id,locator,text FROM passages WHERE source_version_id=? ORDER BY rowid", (row["id"],))]))
    return WebAuditResponse(case_id=case_id, queries=queries, snapshots=snapshots)


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
    identity = hashlib.sha256(db.dumps([case_id,actor.actor_id,request.idempotency_key]).encode("utf-8")).hexdigest()
    key = "upload:"+identity
    previous = read.rows("SELECT event_id FROM events WHERE idempotency_key=?",(key,))
    if previous:
        return AdmitResult(event_id=previous[0]["event_id"],outcome="DUPLICATE",reason="Idempotency key already recorded",job_id=None,stale_fields=[])
    if request.content.kind == "TEXT" and not request.content.text.strip():
        raise HTTPException(422,"Evidence text must not be blank")
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
