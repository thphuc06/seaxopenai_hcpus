"""Validate every mock S1 response against P1's concrete transport boundary."""
import json
from pathlib import Path
import subprocess

from pydantic import TypeAdapter
from app.api.contracts import (
    EvidenceResponse, EventCatalogItem, EventLogItem, MetricsResponse,
    ProductResponse, ResetResponse, RunDetailResponse, RunResponse,
)
from app.models import AdmitResult, PassportResponse

FRONTEND = Path(__file__).resolve().parents[1]


def test_all_s1_preview_responses_match_published_contract() -> None:
    result = subprocess.run(
        ["node", "tests/emit_s1_responses.mjs"], cwd=FRONTEND,
        check=True, capture_output=True, encoding="utf-8", timeout=30,
    )
    responses = json.loads(result.stdout)
    contracts = {
        "products": list[ProductResponse], "catalog": list[EventCatalogItem],
        "admitted": AdmitResult, "runs": list[RunResponse], "passport": PassportResponse,
        "evidence": list[EvidenceResponse], "detail": RunDetailResponse,
        "metrics": MetricsResponse, "events": list[EventLogItem], "reset": ResetResponse,
    }
    for key, model in contracts.items():
        TypeAdapter(model).validate_python(responses[key])
    assert len(responses["passport"]["fields"]) == 5
    assert responses["metrics"]["model_calls"]["live"] == 0
    assert responses["admitted"]["outcome"] == "ADMITTED"
