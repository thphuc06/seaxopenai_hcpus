"""S4 transport contracts; workflow implementation follows the checkpoint."""
from typing import Annotated, Literal

from pydantic import Field, JsonValue

from app.models import Citation, ContractModel, DatasetOrigin, PassportField, PassportResponse


class OrderRequest(ContractModel):
    product_id: Annotated[str, Field(min_length=1, pattern=r"\S")]


class ReceiptFieldDiff(ContractModel):
    field_key: str
    then: PassportField | None
    now: PassportField | None
    changed: bool


class ReceiptResponse(ContractModel):
    id: str
    product_id: str
    case_id: str
    placed_at: str
    case_revision: int
    snapshot: PassportResponse
    snapshot_hash: str
    chain_head: str | None
    hash_valid: bool
    changed_since_purchase: bool
    diff: list[ReceiptFieldDiff]


class MarketplaceValueTally(ContractModel):
    value: dict[str, JsonValue]
    display: str
    independent_clusters: int


class MarketplaceFieldTally(ContractModel):
    field_key: str
    independent_clusters: int
    values: list[MarketplaceValueTally]
    majority: dict[str, JsonValue] | None


class BuyerMarketplaceResponse(ContractModel):
    audience: Literal["BUYER"] = "BUYER"
    product_id: str
    scan_id: str | None
    fields: list[MarketplaceFieldTally]


class MarketplaceSellerFinding(ContractModel):
    seller_source_id: str
    shop: str
    field_key: str
    value: dict[str, JsonValue]
    display: str
    cluster: str
    outlier: bool
    citation: Citation
    dataset_origin: DatasetOrigin


class ExpertMarketplaceResponse(ContractModel):
    audience: Literal["EXPERT"] = "EXPERT"
    product_id: str
    scan_id: str | None
    fields: list[MarketplaceFieldTally]
    findings: list[MarketplaceSellerFinding]


class MarketplaceScanResponse(ContractModel):
    product_id: str
    scan_id: str
    sellers_processed: int
    sellers_skipped: int
    findings: int
    llm_mode: Literal["LIVE", "REPLAY", "FALLBACK"]
    stop_reason: str | None


class WebAuditResult(ContractModel):
    url: str
    domain: str
    page_class: str = Field(alias="class")
    score: float | None
    decision: str
    reason: str


class WebAuditQuery(ContractModel):
    id: str
    run_id: str
    query: str
    provider: str
    mode: Literal["LIVE", "REPLAY", "FALLBACK"]
    results: list[WebAuditResult]
    created_at: str


class WebSnapshotPassage(ContractModel):
    id: str
    locator: str
    text: str


class WebAuditSnapshot(ContractModel):
    source_version_id: str
    url: str
    sha256: str
    captured_at: str
    dataset_origin: DatasetOrigin
    identity_verified: bool
    passages: list[WebSnapshotPassage]


class WebAuditResponse(ContractModel):
    case_id: str
    queries: list[WebAuditQuery]
    snapshots: list[WebAuditSnapshot]
