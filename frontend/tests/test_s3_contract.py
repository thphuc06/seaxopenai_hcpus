"""Validate actual preview response bodies with contract-3 Pydantic models."""
import json
from pathlib import Path
import subprocess


def test_s3_preview_wire_contracts() -> None:
    from app.api.glassbox_contracts import BuyerExplanation, ExpertExplanation, GraphResponse, ChainResponse, SearchResponse
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(["node", "tests/emit_s3_responses.mjs"], cwd=root, capture_output=True, encoding="utf-8", check=True, timeout=30)
    data = json.loads(result.stdout)
    for name, model in {"buyer": BuyerExplanation, "expert": ExpertExplanation, "graph": GraphResponse, "chain": ChainResponse, "search": SearchResponse}.items():
        model.model_validate(data[name])
    assert "rules" not in data["buyer"]
    assert data["expert"]["audience"] == "EXPERT"
