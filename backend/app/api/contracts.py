"""P1 S1 transport contracts; shared findings stay in app.models."""
from typing import Literal

from pydantic import JsonValue

from app.models import (
    AdmitResult, Citation, ContractModel, DatasetOrigin, EventResource,
    EventType, RunStatus,
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
