"""Validate S2 preview transport against the merged contract-2 models."""
import json
from pathlib import Path
import subprocess


def test_s2_preview_payloads_match_contract_and_durable_history() -> None:
    from pydantic import TypeAdapter
    from app.api.contracts import (
        CaseHistoryResponse, EvidenceUploadRequest, ReviewQueueItem,
        ReviewRequest, ReviewResponse,
    )
    from app.models import AdmitResult

    frontend = Path(__file__).resolve().parents[1]
    output = subprocess.run(["node", "tests/emit_s2_responses.mjs"], cwd=frontend,
                            check=True, capture_output=True, encoding="utf-8", timeout=30)
    responses = json.loads(output.stdout)
    contracts = {"queue": list[ReviewQueueItem], "reviewRequest": ReviewRequest,
                 "review": ReviewResponse, "history": CaseHistoryResponse,
                 "uploadRequest": EvidenceUploadRequest, "uploaded": AdmitResult}
    for key, model in contracts.items():
        TypeAdapter(model).validate_python(responses[key])
    assert responses["history"]["reviews"][0]["id"] == responses["review"]["id"]
