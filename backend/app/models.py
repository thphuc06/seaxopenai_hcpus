"""Shared contracts from docs/04, docs/05 and team-plan README section 7."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, JsonValue

PUBLIC_FIELDS = (
    "volume", "skin_type", "key_ingredients",
    "notification_number", "responsible_company",
)


class Verdict(StrEnum):
    CONSISTENT = "CONSISTENT"
    CONFLICTING = "CONFLICTING"
    SINGLE_SOURCE = "SINGLE_SOURCE"
    INSUFFICIENT = "INSUFFICIENT"
    UNCERTAIN = "UNCERTAIN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ConflictLocus(StrEnum):
    WITHIN_SOURCE = "WITHIN_SOURCE"
    ACROSS_SOURCES = "ACROSS_SOURCES"
    LISTING_VS_SOURCE = "LISTING_VS_SOURCE"


class ScopeMatch(StrEnum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    UNKNOWN = "UNKNOWN"
    AGENT = "AGENT"


class Freshness(StrEnum):
    CURRENT = "CURRENT"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class Readability(StrEnum):
    READABLE = "READABLE"
    PARTIAL = "PARTIAL"
    UNREADABLE = "UNREADABLE"


class ReviewState(StrEnum):
    AUTO_DRAFT = "AUTO_DRAFT"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    REVIEWED = "REVIEWED"
    SUPERSEDED = "SUPERSEDED"


class EvidenceLevel(StrEnum):
    LISTING = "LISTING"
    PRODUCT_VERSION = "PRODUCT_VERSION"
    BATCH = "BATCH"
    UNIT = "UNIT"


class DatasetOrigin(StrEnum):
    REAL = "REAL"
    SYNTHETIC = "SYNTHETIC"


class SourceKind(StrEnum):
    LISTING = "LISTING"
    BRAND_PAGE = "BRAND_PAGE"
    NOTIFICATION_DOC = "NOTIFICATION_DOC"
    PACKAGING_IMAGE = "PACKAGING_IMAGE"
    SELLER_UPLOAD = "SELLER_UPLOAD"
    REGISTRY_RECORD = "REGISTRY_RECORD"
    WEB_PAGE = "WEB_PAGE"


class SourceStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    REVOKED = "REVOKED"
    UNAVAILABLE = "UNAVAILABLE"


class RunStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    WAITING_EVIDENCE = "WAITING_EVIDENCE"
    WAITING_REVIEW = "WAITING_REVIEW"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Role(StrEnum):
    BUYER = "BUYER"
    SELLER = "SELLER"
    REVIEWER = "REVIEWER"
    OPERATOR = "OPERATOR"
    SYSTEM = "SYSTEM"


class EventType(StrEnum):
    BOOTSTRAP = "BOOTSTRAP"
    LISTING_CHANGED = "LISTING_CHANGED"
    SOURCE_CHANGED = "SOURCE_CHANGED"
    EVIDENCE_ADDED = "EVIDENCE_ADDED"
    SOURCE_REVOKED = "SOURCE_REVOKED"
    WEB_SEARCH_REQUESTED = "WEB_SEARCH_REQUESTED"


class EventOutcome(StrEnum):
    ADMITTED = "ADMITTED"
    NOOP = "NOOP"
    DUPLICATE = "DUPLICATE"
    REJECTED = "REJECTED"


class SkinType(StrEnum):
    DRY = "DRY"
    NORMAL = "NORMAL"
    OILY = "OILY"
    COMBINATION = "COMBINATION"
    SENSITIVE = "SENSITIVE"
    ACNE_PRONE = "ACNE_PRONE"
    ALL = "ALL"


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EventResource(ContractModel):
    kind: Literal["LISTING", "SOURCE", "CASE"]
    id: str
    version: int


class EventEnvelope(ContractModel):
    event_id: str
    idempotency_key: str
    type: EventType
    schema_version: Literal["1"]
    producer: str
    resource: EventResource
    changed_fields: list[str]
    payload: dict[str, JsonValue]
    occurred_at: str
    correlation_id: str


class AdmitResult(ContractModel):
    event_id: str
    outcome: EventOutcome
    reason: str
    job_id: str | None
    stale_fields: list[str]


class ExtractedClaim(ContractModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    field_key: Literal[
        "volume", "skin_type", "key_ingredients", "inci_list",
        "notification_number", "responsible_company",
    ]
    raw_value: str | None
    passage_id: str
    quote: str | None
    readability: Literal["READABLE", "PARTIAL", "UNREADABLE"]
    proposed_skin_types: list[Literal[
        "DRY", "NORMAL", "OILY", "COMBINATION", "SENSITIVE", "ACNE_PRONE", "ALL",
    ]] | None
    proposed_ingredients: list[str] | None
    proposed_volume_ml: float | None


class ClaimExtraction(ContractModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source_version_id: str
    claims: list[ExtractedClaim]
    ignored_instructions_detected: bool


class Citation(ContractModel):
    passage_id: str
    source_kind: SourceKind
    source_version: int
    locator: str
    excerpt: str


class RuleStep(ContractModel):
    rule: str
    outcome: str
    detail: str


class DependsOn(ContractModel):
    source_id: str
    source_version_id: str


class Gap(ContractModel):
    field_key: str
    missing_kind: str
    needed_doc: str
    known_ids: list[str]
    reason: str


class FieldDecision(ContractModel):
    field_key: str
    verdict: Verdict
    conflict_locus: ConflictLocus | None
    scope_match: ScopeMatch
    review_state: ReviewState
    evidence_level: EvidenceLevel
    seller_attributable: bool
    citations: list[Citation]
    depends_on: list[DependsOn]
    public_text: str
    notes: list[str]
    explain: list[RuleStep]
    gap: Gap | None
    needs_scope_resolution: bool


class PassportField(ContractModel):
    field_key: str
    label: str
    public_text: str
    verdict: Verdict
    conflict_locus: ConflictLocus | None
    freshness: Freshness
    review_state: ReviewState
    checked_at: str | None
    citations: list[Citation]


class ClaimFinding(FieldDecision):
    """Expert claim findings use the same policy decision contract (S2)."""


class PassportResponse(ContractModel):
    product_id: str
    dataset_origin: DatasetOrigin
    last_checked_at: str | None
    run_status: RunStatus | None
    fields: list[PassportField]
    disclaimer: str
