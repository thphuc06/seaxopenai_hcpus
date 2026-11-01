from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

from app.api import scorecard
from app.main import create_app
from app.models import Verdict
from p1_helpers import CoreDB, core_db

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.eval import FieldComparison
from scripts.metrics import field_metrics


def field(expected: str, actual: str | None, *, blame: bool = False) -> FieldComparison:
    return FieldComparison(field_key="volume", expected=Verdict(expected), candidate=Verdict(actual) if actual else None,
        b0=Verdict.INSUFFICIENT, b0_seller_attributable=False, candidate_seller_attributable=blame,
        expected_seller_attributable=False)


def test_metric_denominators_include_missing_but_separate_abstention() -> None:
    result = field_metrics([field("CONSISTENT", "CONSISTENT"), field("CONFLICTING", "INSUFFICIENT"), field("CONSISTENT", None),
                            field("SINGLE_SOURCE", "CONFLICTING", blame=True)])
    assert result.fields == 4 and result.missing_predictions == 1
    assert result.accuracy == 0.25 and result.abstention_rate == 0.25
    assert result.coverage == result.selective_accuracy == 0.5
    assert result.conflict_precision == result.conflict_recall == 0
    assert result.macro_f1 == pytest.approx(1 / 6)
    assert result.seller_false_blame_rate == 0.25
    empty = field_metrics([])
    assert empty.accuracy is empty.macro_f1 is empty.conflict_precision is None
    abstained = field_metrics([field("UNCERTAIN", "UNCERTAIN")])
    assert abstained.accuracy == 1 and abstained.coverage == 0 and abstained.selective_accuracy is None


def test_cached_scorecard_acl_absence_validation_and_no_writes(core_db: CoreDB, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "metrics.json"
    monkeypatch.setattr(scorecard, "SCORECARD_PATH", path)
    before = core_db.dump()
    with TestClient(create_app()) as client:
        url = "/api/internal/eval/metrics"
        for role in ("BUYER", "SELLER", "SYSTEM"):
            assert client.get(url, headers={"X-Demo-Role": role, "X-Demo-Actor": "reader"}).status_code == 403
        headers = {"X-Demo-Role": "REVIEWER", "X-Demo-Actor": "reader"}
        assert client.get(url, headers=headers).json() == {"available": False}
        report = scorecard.Scorecard(generated_at="2026-11-01", evaluated_at="2026-10-31", source_sha256="a" * 64,
            mode="fallback", requested_mode="replay", fallback_reason="REPLAY_MISS", gold_status="DRAFT", models=[],
            prompt_versions=[], policy_versions=["test"], metrics_by_gold_status={"DRAFT": field_metrics([])},
            model_calls=0, tokens_in=0, tokens_out=0, limitations=["DRAFT diagnostics only"])
        path.write_text(report.model_dump_json(), encoding="utf-8")
        assert client.get(url, headers=headers).json() == report.model_dump(mode="json")
        path.write_text('{"secret": "DO NOT RETURN"}', encoding="utf-8")
        response = client.get(url, headers=headers)
        assert response.status_code == 503 and "DO NOT RETURN" not in response.text
    assert core_db.dump() == before
