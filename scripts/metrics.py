"""Summarize an offline eval JSON archive into the expert UI's stored scorecard."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from app.api.scorecard import Metrics, Scorecard
from app.models import Verdict
from scripts.eval import EvaluationReport, FieldComparison


def ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def field_metrics(fields: list[FieldComparison]) -> Metrics:
    correct = sum(f.candidate == f.expected for f in fields)
    classes = {f.expected for f in fields} | {f.candidate for f in fields if f.candidate is not None}
    f1: list[float] = []
    for label in classes:
        true = sum(f.candidate == label and f.expected == label for f in fields)
        denominator = sum(f.candidate == label for f in fields) + sum(f.expected == label for f in fields)
        f1.append(2 * true / denominator)
    conflicts = sum(f.candidate == Verdict.CONFLICTING for f in fields)
    expected_conflicts = sum(f.expected == Verdict.CONFLICTING for f in fields)
    matched_conflicts = sum(f.candidate == f.expected == Verdict.CONFLICTING for f in fields)
    decided = [f for f in fields if f.candidate is not None and f.candidate not in {Verdict.INSUFFICIENT, Verdict.UNCERTAIN}]
    attributable = [f for f in fields if f.expected_seller_attributable is False and f.candidate_seller_attributable is not None]
    return Metrics(fields=len(fields), missing_predictions=sum(f.candidate is None for f in fields),
        accuracy=ratio(correct, len(fields)), macro_f1=sum(f1)/len(f1) if f1 else None,
        conflict_precision=ratio(matched_conflicts, conflicts), conflict_recall=ratio(matched_conflicts, expected_conflicts),
        seller_false_blame_rate=ratio(sum(f.candidate_seller_attributable is True for f in attributable), len(attributable)),
        seller_attribution_scored=len(attributable),
        abstention_rate=ratio(sum(f.candidate in {Verdict.INSUFFICIENT, Verdict.UNCERTAIN} for f in fields), len(fields)),
        coverage=ratio(len(decided), len(fields)), selective_accuracy=ratio(sum(f.candidate == f.expected for f in decided), len(decided)))


def summarize(report: EvaluationReport, source_hash: str) -> Scorecard:
    return Scorecard(generated_at=datetime.now(timezone.utc).isoformat(), evaluated_at=report.generated_at,
        source_sha256=source_hash, mode=report.mode, requested_mode=report.requested_mode,
        fallback_reason=report.fallback_reason, gold_status=report.gold_status, models=report.models,
        prompt_versions=report.prompt_versions, policy_versions=report.policy_versions,
        metrics_by_gold_status={status: field_metrics([f for point in report.checkpoints if point.status == status for f in point.fields])
                               for status in ("DRAFT", "REVIEWED")},
        model_calls=report.usage.model_calls, tokens_in=report.usage.tokens_in, tokens_out=report.usage.tokens_out,
        limitations=[*report.limitations,
            *[f"Checkpoint {point.event}: {point.error or ', '.join(point.stop_reasons)}; inspect the evaluation archive."
              for point in report.checkpoints if point.error or point.stop_reasons],
            "Candidate-only metrics; missing predictions count as incorrect and remain separate from abstentions.",
            "Macro F1 averages labels present in expected or predicted values; zero denominators are null.",
            "Only explicitly non-attributable labels with a recorded candidate attribution enter the false-blame denominator.",
            "Citation validity, event freshness, provider costs and metamorphic execution are not measured by this scorecard.",
            "Previous replay attempts are excluded from fallback scores; inspect the source eval archive for their errors and usage."])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="EvaluationReport JSON produced by scripts/eval.py")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "docs/results")
    args = parser.parse_args()
    payload = args.input.read_bytes()
    report = summarize(EvaluationReport.model_validate_json(payload), sha256(payload).hexdigest())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    text = report.model_dump_json(indent=2) + "\n"
    archive = args.output_dir / f"metrics-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{uuid4().hex}.json"
    with archive.open("x", encoding="utf-8") as stream:
        stream.write(text)
    # Atomic replacement: concurrent readers see either complete scorecard, never half a JSON file.
    pending = args.output_dir / f".metrics-{uuid4().hex}.tmp"
    pending.write_text(text, encoding="utf-8")
    pending.replace(args.output_dir / "metrics.json")
    print(f"Scorecard written; mode={report.mode}, gold={report.gold_status}, archive={archive.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
