"""S3 transport schemas; public explanations and expert records are separate."""
from typing import Literal

from pydantic import JsonValue

from app.api.contracts import EvidencePassage, ModelCallCounts, ReviewResponse
from app.models import ContractModel, RuleStep


class BuyerExplanation(ContractModel):
    audience: Literal["BUYER"] = "BUYER"
    product_id: str
    field_key: str
    public_text: str
    summaries: list[str]
    citations: list[EvidencePassage]
    hidden_citations: int


class ExplainSource(ContractModel):
    source_version_id: str
    sha256: str
    captured_at: str
    origin: str


class ExplainClaim(ContractModel):
    source_version_id: str
    passage_id: str
    quote: str | None
    extractor: str
    prompt_version: str
    mapped_by: str | None


class ExpertExplanation(ContractModel):
    audience: Literal["EXPERT"] = "EXPERT"
    product_id: str
    field_key: str
    result_id: str
    trigger_event_id: str
    sources: list[ExplainSource]
    claims: list[ExplainClaim]
    rules: list[RuleStep]
    publish_checks: list[str]
    chain_head: str | None
    reviews: list[ReviewResponse]


class ObservabilityResponse(ContractModel):
    verdicts: dict[str, int]
    model_calls: ModelCallCounts
    calls_by_step: dict[str, ModelCallCounts]
    publish_passed: int
    publish_blocked: int
    agent_stops: dict[str, int]
    gap_stops: dict[str, int]
    vocabulary: dict[str, int]
    review_queue_size: int
    oldest_review_age_s: float | None


class ChainResponse(ContractModel):
    valid: bool
    rows: int
    head: str | None = None
    broken_at: int | None = None


class GraphNode(ContractModel):
    id: str
    kind: Literal["source", "field"]
    label: str
    status: str


class GraphEdge(ContractModel):
    source: str
    target: str
    relation: Literal["depends_on", "cites"]


class GraphResponse(ContractModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class SearchResponse(ContractModel):
    hits: list[dict[str, JsonValue]]
    stages: dict[str, list[dict[str, JsonValue]]]


class OtelResponse(ContractModel):
    resourceSpans: list[dict[str, JsonValue]]
