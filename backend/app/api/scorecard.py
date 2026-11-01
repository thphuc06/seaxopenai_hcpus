"""Read a validated offline scorecard. Application code never runs evaluation."""
from pathlib import Path
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

SCORECARD_PATH = Path(__file__).resolve().parents[3] / "docs" / "results" / "metrics.json"


class Metrics(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fields: int = Field(ge=0)
    missing_predictions: int = Field(ge=0)
    accuracy: float | None = Field(ge=0, le=1)
    macro_f1: float | None = Field(ge=0, le=1)
    conflict_precision: float | None = Field(ge=0, le=1)
    conflict_recall: float | None = Field(ge=0, le=1)
    seller_false_blame_rate: float | None = Field(ge=0, le=1)
    seller_attribution_scored: int = Field(ge=0)
    abstention_rate: float | None = Field(ge=0, le=1)
    coverage: float | None = Field(ge=0, le=1)
    selective_accuracy: float | None = Field(ge=0, le=1)


class Scorecard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    available: Literal[True] = True
    format_version: Literal[1] = 1
    generated_at: str
    evaluated_at: str
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mode: Literal["fallback", "replay"]
    requested_mode: Literal["fallback", "replay"]
    fallback_reason: str | None
    gold_status: Literal["DRAFT", "REVIEWED"]
    models: list[str]
    prompt_versions: list[str]
    policy_versions: list[str]
    metrics_by_gold_status: dict[Literal["DRAFT", "REVIEWED"], Metrics]
    model_calls: int = Field(ge=0)
    tokens_in: int = Field(ge=0)
    tokens_out: int = Field(ge=0)
    limitations: list[str]


def stored_metrics() -> dict[str, JsonValue]:
    try:
        with SCORECARD_PATH.open("rb") as stream:
            payload = stream.read(2_000_001)
    except FileNotFoundError:
        return {"available": False}
    except OSError as error:
        raise HTTPException(503, "Stored scorecard could not be read") from error
    try:
        if len(payload) > 2_000_000:
            raise ValueError("Scorecard too large")
        return Scorecard.model_validate_json(payload).model_dump(mode="json")
    except (ValueError, ValidationError) as error:
        raise HTTPException(503, "Stored scorecard is invalid; regenerate it offline") from error
