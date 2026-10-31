"""P1 S1 transport contracts; shared findings stay in app.models."""
from typing import Annotated, Literal

from pydantic import Field, JsonValue

from app.models import (
    AdmitResult, Citation, ContractModel, DatasetOrigin, EventResource,
    EventType, RunStatus, Verdict, ReviewState, PassportField,
)


class PassportMetadata(ContractModel):
    llm_mode: Literal["LIVE", "REPLAY", "FALLBACK"] | None = None
    hidden_citations: dict[str, int]


class ProductPresentation(ContractModel):
    image: str
    image_alt: str
    price: float
    currency: str
    shop: str
    official_store: bool
    category: str
    passport_metadata: PassportMetadata | None = None


class ProductResponse(ContractModel):
    id: str
    name: str
    brand: str
    variant: str
    market: str
    dataset_origin: DatasetOrigin
    presentation: ProductPresentation | None = None


class EvidencePassage(Citation):
    text: str
    source_label: str
    captured_at: str
    visibility: Literal["PUBLIC", "PRIVATE"]


class EvidenceResponse(ContractModel):
    citations: list[EvidencePassage]
    hidden_citations: int


class EventCatalogItem(ContractModel):
    name: str
    title: str
    type: EventType
    product_id: str
    resource: EventResource
    expect: str


class EventLogItem(AdmitResult):
    received_at: str
    run_id: str | None


class RunUsage(ContractModel):
    model_calls: int
    tokens_in: int
    tokens_out: int


class RunResponse(ContractModel):
    id: str
    case_id: str
    case_revision: int
    trigger_event_id: str
    status: RunStatus
    stop_reason: str | None
    llm_mode: Literal["LIVE", "REPLAY", "FALLBACK"]
    started_at: str | None
    finished_at: str | None
    usage: RunUsage


class TraceStepResponse(ContractModel):
    id: str
    run_id: str
    seq: int
    step: str
    actor: Literal["code", "llm", "human"]
    input_refs: list[str]
    output_refs: list[str]
    latency_ms: float
    tokens_in: int
    tokens_out: int
    error: str | None
    detail: dict[str, JsonValue]
    created_at: str
    t_ms: float


class RunDetailResponse(ContractModel):
    run: RunResponse
    steps: list[TraceStepResponse]


class EventCounts(ContractModel):
    ADMITTED: int
    NOOP: int
    DUPLICATE: int
    REJECTED: int


class ModelCallCounts(ContractModel):
    live: int
    replayed: int
    avoided: int


class MetricsResponse(ContractModel):
    events: EventCounts
    runs: int
    jobs: int
    model_calls: ModelCallCounts
    passport_reads: int


class ResetResponse(ContractModel):
    status: str


ReviewDecision = Literal["APPROVE", "OVERRIDE", "REJECT"]


class ReviewOverride(ContractModel):
    verdict: Verdict
    citations: list[Citation]
    public_text: str = Field(min_length=1)


class ReviewRequest(ContractModel):
    result_id: str = Field(min_length=1)
    case_revision: int = Field(ge=0, strict=True)
    decision: ReviewDecision
    reason: str = Field(min_length=1)
    override: ReviewOverride | None = None


class ReviewResponse(ContractModel):
    id: str
    case_id: str
    result_id: str
    case_revision: int
    reviewer_id: str
    decision: ReviewDecision
    reason: str
    override: ReviewOverride | None
    created_at: str
    review_state: ReviewState


class ReviewQueueItem(ContractModel):
    id: str
    case_id: str
    field_key: str
    result_id: str
    case_revision: int
    reason_code: str
    verdict: Verdict


class ResultVersionResponse(PassportField):
    id: str
    case_id: str
    result_version: int
    case_revision: int
    created_at: str
    superseded_by: str | None


class EvidenceRequestResponse(ContractModel):
    id: str
    case_id: str
    field_key: str
    gap_id: str
    reason: str
    requested_from: Literal["SELLER", "BRAND"]
    status: Literal["OPEN", "FULFILLED"]
    created_at: str


class CaseHistoryResponse(ContractModel):
    case_id: str
    case_revision: int
    results: list[ResultVersionResponse]
    events: list[EventLogItem]
    reviews: list[ReviewResponse]
    requests: list[EvidenceRequestResponse]


class TextEvidence(ContractModel):
    kind: Literal["TEXT"]
    text: str = Field(min_length=1)


class ImageEvidence(ContractModel):
    kind: Literal["IMAGE"]
    media_type: Literal["image/png", "image/jpeg"]
    data_base64: str = Field(min_length=1)


class EvidenceUploadRequest(ContractModel):
    idempotency_key: str = Field(min_length=1)
    field_keys: list[str] = Field(min_length=1)
    content: Annotated[TextEvidence | ImageEvidence, Field(discriminator="kind")]
