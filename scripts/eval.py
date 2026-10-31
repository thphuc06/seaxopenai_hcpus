"""Offline B0/candidate diagnostic, with optional capped B1 and immutable archives."""
from __future__ import annotations

import argparse
from collections.abc import Sequence
from contextlib import closing
from datetime import datetime, timezone
import hashlib
from io import TextIOWrapper
import json
import os
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
from typing import Literal
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import BaseModel, Field, JsonValue, model_validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from app.models import AdmitResult, EventOutcome, PUBLIC_FIELDS, PassportResponse, Readability, SourceKind, Verdict
from app.pipeline.baseline import BASELINE_VERSION, BaselineClaim, BaselineFinding, compare_claims
from scripts.sync_check import HEADERS, isolated_settings
from scripts.baseline_eval import B1Report, B1Session

GoldStatus = Literal["DRAFT", "REVIEWED"]
Mode = Literal["fallback", "replay"]


class GoldCheckpoint(BaseModel):
    # Evidence, rationale and scenario variants are preserved in the original file.
    after_event: str
    product_id: str
    case_id: str
    expected: dict[str, Verdict]
    outcome: EventOutcome | None = None
    status: GoldStatus | None = None
    reviewed_by: str | None = None
    invariants: dict[str, JsonValue] = Field(default_factory=dict)
    preconditions: list[str] = Field(default_factory=list)


class GoldFile(BaseModel):
    status: GoldStatus
    labelled_by: str
    reviewed_by: str | None = None
    event_order: list[str] = Field(default_factory=list)
    checkpoints: list[GoldCheckpoint]

    @model_validator(mode="after")
    def valid_review_and_order(self) -> GoldFile:
        events = [checkpoint.after_event for checkpoint in self.checkpoints]
        if len(set(events)) != len(events):
            raise ValueError("Duplicate checkpoint event")
        if self.event_order and events != self.event_order:
            raise ValueError("Checkpoint order must match the declared event_order")
        for checkpoint in self.checkpoints:
            if not checkpoint.expected or set(checkpoint.expected) - set(PUBLIC_FIELDS):
                raise ValueError("Expected labels must name public fields")
            if (checkpoint.status or self.status) == "REVIEWED":
                reviewer = checkpoint.reviewed_by or self.reviewed_by
                if not reviewer or reviewer.lower().startswith("draft:"):
                    raise ValueError("REVIEWED labels require a named human reviewer")
        return self


class Score(BaseModel):
    total: int = 0
    correct: int = 0
    false_blame: int = 0
    false_blame_eligible: int = 0
    abstentions: int = 0
    expected_abstentions: int = 0
    correct_abstentions: int = 0

    def add(self, other: Score) -> None:
        for name in type(self).model_fields:
            setattr(self, name, getattr(self, name) + getattr(other, name))


class Usage(BaseModel):
    model_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: float = 0

    def add(self, other: Usage) -> None:
        self.model_calls += other.model_calls
        self.tokens_in += other.tokens_in
        self.tokens_out += other.tokens_out
        self.latency_ms += other.latency_ms


class FieldComparison(BaseModel):
    field_key: str
    expected: Verdict
    b0: Verdict
    candidate: Verdict | None
    b0_seller_attributable: bool
    candidate_seller_attributable: bool | None
    expected_seller_attributable: bool | None
    b1: Verdict | None = None
    b1_seller_attributable: bool | None = None


class CheckpointReport(BaseModel):
    event: str
    product_id: str
    status: GoldStatus
    reviewed_by: str | None
    outcome: str | None
    expected_outcome: EventOutcome | None = None
    error: str | None = None
    preconditions: list[str]
    fields: list[FieldComparison]
    scores: dict[str, Score]
    usage: Usage
    run_ids: list[str]
    run_statuses: list[str]
    stop_reasons: list[str]
    b1: B1Report = Field(default_factory=B1Report)


class EvaluationReport(BaseModel):
    generated_at: str
    requested_mode: Mode
    mode: Mode
    fallback_reason: str | None = None
    baseline_version: str = BASELINE_VERSION
    gold_status: GoldStatus
    labelled_by: str
    gold_sha256: str
    models: list[str]
    prompt_versions: list[str]
    policy_versions: list[str]
    checkpoints: list[CheckpointReport]
    totals: dict[str, dict[str, Score]]
    usage: Usage
    limitations: list[str]
    previous_attempt: EvaluationReport | None = None


class StoredClaim(BaseModel):
    source_kind: SourceKind
    field_key: str
    raw_value: str | None
    normalized_json: str
    readability: Readability


class StoredResult(BaseModel):
    field_key: str
    verdict: Verdict
    seller_attributable: bool


class StoredRun(BaseModel):
    id: str
    status: str
    stop_reason: str | None
    model: str | None
    prompt_version: str | None
    policy_version: str | None
    usage_json: str | None


class TraceProvenance(BaseModel):
    model: str | None = None
    prompt_version: str | None = None


def model_metadata(runs: list[StoredRun], steps: list[TraceProvenance]) -> tuple[list[str], list[str]]:
    return (sorted({run.model for run in runs if run.model} | {step.model for step in steps if step.model}),
            sorted({run.prompt_version for run in runs if run.prompt_version}
                   | {step.prompt_version for step in steps if step.prompt_version}))


class Counter(BaseModel):
    used: float = 0


class Tokens(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class StoredUsage(BaseModel):
    model_calls: Counter = Field(default_factory=Counter)
    seconds: Counter = Field(default_factory=Counter)
    tokens: Tokens = Field(default_factory=Tokens)


def read_rows(database: Path, sql: str, parameters: tuple[str, ...] = ()) -> list[dict[str, JsonValue]]:
    with closing(sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute(sql, parameters)]


def stored_baseline(database: Path, case_id: str) -> list[BaselineFinding]:
    claims = [StoredClaim.model_validate(row) for row in read_rows(database,
        "SELECT s.kind AS source_kind,c.field_key,c.raw_value,c.normalized_json,c.readability "
        "FROM claims c JOIN source_versions sv ON sv.id=c.source_version_id "
        "JOIN sources s ON s.id=sv.source_id WHERE s.case_id=? AND sv.is_current=1 "
        "AND s.status='ACTIVE' ORDER BY c.id", (case_id,))]
    inputs: list[BaselineClaim] = []
    for claim in claims:
        normalized: JsonValue = json.loads(claim.normalized_json)
        if not isinstance(normalized, dict):
            raise ValueError("Stored normalized claim must be an object")
        inputs.append(BaselineClaim(claim.source_kind, claim.field_key, claim.raw_value,
                                    normalized, claim.readability))
    return compare_claims(inputs)


def expected_attribution(checkpoint: GoldCheckpoint, field: str) -> bool | None:
    invariant = checkpoint.invariants.get(field)
    if isinstance(invariant, dict) and isinstance(invariant.get("seller_attributable"), bool):
        return invariant["seller_attributable"]
    return False if checkpoint.expected[field] != Verdict.CONFLICTING else None


def score_fields(fields: list[FieldComparison], system: Literal["B0", "B1", "candidate"]) -> Score:
    score = Score(total=len(fields))
    for field in fields:
        actual = field.b0 if system == "B0" else field.b1 if system == "B1" else field.candidate
        blamed = (field.b0_seller_attributable if system == "B0" else field.b1_seller_attributable
                  if system == "B1" else field.candidate_seller_attributable)
        score.correct += actual == field.expected
        abstained = actual in {Verdict.INSUFFICIENT, Verdict.UNCERTAIN}
        expected_abstain = field.expected in {Verdict.INSUFFICIENT, Verdict.UNCERTAIN}
        score.abstentions += abstained
        score.expected_abstentions += expected_abstain
        score.correct_abstentions += abstained and expected_abstain
        if field.expected_seller_attributable is False:
            score.false_blame_eligible += 1
            score.false_blame += actual == Verdict.CONFLICTING and blamed is True
    return score


def evaluate_checkpoint(client: TestClient, database: Path, checkpoint: GoldCheckpoint,
                        gold: GoldFile, seen_runs: set[str]) -> tuple[CheckpointReport, list[StoredRun]]:
    response = client.post(f"/api/internal/demo/fire/{checkpoint.after_event}", headers=HEADERS["OPERATOR"])
    outcome = None
    error = None
    if response.is_success:
        outcome = AdmitResult.model_validate(response.json()).outcome.value
        if checkpoint.outcome is not None and outcome != checkpoint.outcome:
            error = f"event outcome {outcome}, expected {checkpoint.outcome.value}"
    else:
        error = f"event HTTP {response.status_code}"
    response = client.get(f"/api/products/{checkpoint.product_id}/passport", headers=HEADERS["REVIEWER"])
    passport = PassportResponse.model_validate(response.json()) if response.is_success else None
    if passport is None:
        error = f"{error + '; ' if error else ''}passport HTTP {response.status_code}"
    current = {row.field_key: row for row in (StoredResult.model_validate(row) for row in read_rows(
        database, "SELECT field_key,verdict,seller_attributable FROM field_results "
        "WHERE case_id=? AND superseded_by IS NULL", (checkpoint.case_id,)))}
    public = {field.field_key: field.verdict for field in passport.fields} if passport else {}
    baseline = {field.field_key: field for field in stored_baseline(database, checkpoint.case_id)}
    fields = [FieldComparison(field_key=key, expected=expected,
        b0=baseline[key].verdict, b0_seller_attributable=baseline[key].seller_attributable,
        candidate=public.get(key), candidate_seller_attributable=current[key].seller_attributable if key in current else None,
        expected_seller_attributable=expected_attribution(checkpoint, key)) for key, expected in checkpoint.expected.items()]
    runs = [StoredRun.model_validate(row) for row in read_rows(database,
        "SELECT id,status,stop_reason,model,prompt_version,policy_version,usage_json FROM runs ORDER BY created_at,id")
        if str(row["id"]) not in seen_runs]
    seen_runs.update(run.id for run in runs)
    usage = Usage()
    for run in runs:
        stored = StoredUsage.model_validate_json(run.usage_json or "{}")
        usage.add(Usage(model_calls=int(stored.model_calls.used), tokens_in=stored.tokens.input_tokens,
                        tokens_out=stored.tokens.output_tokens, latency_ms=stored.seconds.used * 1000))
    return CheckpointReport(event=checkpoint.after_event, product_id=checkpoint.product_id,
        status=checkpoint.status or gold.status, reviewed_by=checkpoint.reviewed_by or gold.reviewed_by,
        outcome=outcome, expected_outcome=checkpoint.outcome, error=error,
        preconditions=checkpoint.preconditions, fields=fields,
        scores={system: score_fields(fields, system) for system in ("B0", "candidate")}, usage=usage,
        run_ids=[run.id for run in runs], run_statuses=[run.status for run in runs],
        stop_reasons=[run.stop_reason for run in runs if run.stop_reason]), runs


def run_evaluation(gold: GoldFile, gold_hash: str, mode: Mode, limit: int | None = None,
                   b1_session: B1Session | None = None) -> EvaluationReport:
    from app.main import create_app
    checkpoints: list[CheckpointReport] = []
    all_runs: list[StoredRun] = []
    provenance: list[TraceProvenance] = []
    seen: set[str] = set()
    attempted_network: list[bool] = []

    def deny_network(**request: object) -> None:
        attempted_network.append(True)
        raise RuntimeError("Offline evaluator does not permit provider calls")

    with TemporaryDirectory(prefix="passport-eval-") as directory:
        database = Path(directory) / "eval.db"
        # A process-level replay freeze must not disguise a labelled fallback retry.
        with isolated_settings(mode, database, replay_freeze=False):
            with TestClient(create_app()) as client:
                for checkpoint in gold.checkpoints[:limit]:
                    with patch("app.llm.client._call_api", deny_network):
                        result, runs = evaluate_checkpoint(client, database, checkpoint, gold, seen)
                    if b1_session is not None:
                        result.b1 = b1_session.evaluate(database, checkpoint.case_id)
                        if result.b1.prediction is not None:
                            for field in result.fields:
                                prediction = getattr(result.b1.prediction, field.field_key)
                                field.b1, field.b1_seller_attributable = Verdict(prediction.verdict), prediction.seller_attributable
                            result.scores["B1"] = score_fields(result.fields, "B1")
                    checkpoints.append(result)
                    all_runs.extend(runs)
                    if mode == "replay" and "REPLAY_MISS" in result.stop_reasons:
                        break
                provenance = [TraceProvenance.model_validate_json(str(row["detail"])) for row in read_rows(
                    database, "SELECT detail FROM trace_steps WHERE detail IS NOT NULL AND detail != ''")]
    if attempted_network:
        raise RuntimeError("Offline evaluator attempted a provider call; report not scored")
    totals = {status: {system: Score() for system in ("B0", "B1", "candidate")} for status in ("DRAFT", "REVIEWED")}
    usage = Usage()
    for checkpoint in checkpoints:
        usage.add(checkpoint.usage)
        for system, score in checkpoint.scores.items():
            totals[checkpoint.status][system].add(score)
    models, prompts = model_metadata(all_runs, provenance)
    return EvaluationReport(generated_at=datetime.now(timezone.utc).isoformat(), requested_mode=mode, mode=mode,
        gold_status=gold.status, labelled_by=gold.labelled_by, gold_sha256=gold_hash,
        models=models, prompt_versions=prompts,
        policy_versions=sorted({run.policy_version for run in all_runs if run.policy_version}),
        checkpoints=checkpoints, totals=totals, usage=usage, limitations=[
            "DRAFT scores are exploratory diagnostics, not human-reviewed accuracy.",
            "B0 uses candidate-stored claims; upstream scope/extraction filtering is shared, not an independent extraction baseline.",
            "B0 adds zero model calls. Usage is counted once per newly observed candidate run; NOOP/DUPLICATE do not reuse prior usage.",
            "Literal expected labels are scored; preconditions and alternative gold scenarios are not inferred from candidate output.",
            "Only five public fields are scored; expert claim findings and isolated image scenarios have separate acceptance tests.",
            "False-blame attribution is unscored for expected conflicts without an explicit attribution invariant.",
            "B1 is an unpublished single-call diagnostic over source passages, with separate usage. NOT_RUN/errors/caps are unscored, never zero-accuracy claims.",
        ])


def markdown(report: EvaluationReport) -> str:
    lines = ["# B0 / B1 / candidate evaluation", "", f"Generated: {report.generated_at}",
             f"Mode: {report.mode}; requested: {report.requested_mode}; gold: {report.gold_status}; labelled by: {report.labelled_by}",
             f"Models: {', '.join(report.models) or 'none'}; prompts: {', '.join(report.prompt_versions) or 'none'}; policies: {', '.join(report.policy_versions) or 'none'}",
             f"Baseline: {report.baseline_version}; gold SHA256: {report.gold_sha256}", ""]
    if report.fallback_reason:
        lines += [f"**FALLBACK: {report.fallback_reason}. The complete story was restarted in a fresh DB.**", ""]
    lines += ["## Scores by gold review status", "", "| Gold | System | Correct/total | False blame/eligible | Abstentions | Correct/expected abstentions |",
              "|---|---|---:|---:|---:|---:|"]
    for status, systems in report.totals.items():
        for system, score in systems.items():
            lines.append(f"| {status} | {system} | {score.correct}/{score.total} | {score.false_blame}/{score.false_blame_eligible} | {score.abstentions} | {score.correct_abstentions}/{score.expected_abstentions} |")
    lines += ["", "## Checkpoints", "", "| Event | Gold | B0 | B1 | Candidate | Calls | Tokens in/out | Latency ms | Outcome / stops |",
              "|---|---|---:|---|---:|---:|---:|---:|---|"]
    for point in report.checkpoints:
        b0, candidate = point.scores["B0"], point.scores["candidate"]
        b1 = point.scores.get("B1")
        b1_text = f"{b1.correct}/{b1.total} ({point.b1.status})" if b1 else point.b1.status
        lines.append(f"| {point.event} | {point.status} | {b0.correct}/{b0.total} | {b1_text} | {candidate.correct}/{candidate.total} | {point.usage.model_calls} | {point.usage.tokens_in}/{point.usage.tokens_out} | {point.usage.latency_ms:.2f} | {point.error or point.outcome}; {', '.join(point.stop_reasons)} |")
    lines += ["", "## B1 usage", ""]
    for point in report.checkpoints:
        if point.b1.mode != "off":
            lines.append(f"- {point.event}: model={point.b1.model}; {point.b1.calls} calls; {point.b1.tokens_in}/{point.b1.tokens_out} tokens; {point.b1.status}.")
    lines += ["", "## Disagreements and preconditions", ""]
    for point in report.checkpoints:
        for field in point.fields:
            if field.b0 != field.expected or field.candidate != field.expected or (field.b1 is not None and field.b1 != field.expected):
                lines.append(f"- {point.event} / {field.field_key}: expected {field.expected}; B0 {field.b0}; B1 {field.b1 or 'NOT_RUN'}; candidate {field.candidate or 'MISSING'}.")
        for condition in point.preconditions:
            lines.append(f"- {point.event} precondition: {condition}")
        if point.reviewed_by:
            lines.append(f"- {point.event} reviewed by: {point.reviewed_by}")
    lines += ["", "## Limits", ""] + [f"- {limit}" for limit in report.limitations]
    lines += ["", f"Candidate totals: {report.usage.model_calls} calls, {report.usage.tokens_in}/{report.usage.tokens_out} tokens in/out, {report.usage.latency_ms:.2f} ms."]
    if report.previous_attempt:
        lines += [f"Replay attempt retained in JSON: {report.previous_attempt.usage.model_calls} calls, {len(report.previous_attempt.checkpoints)} checkpoints; excluded from fallback scores."]
    return "\n".join(lines) + "\n"


def write_report(report: EvaluationReport, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    payload = report.model_dump_json(indent=2)
    text = markdown(report)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    for stem in (f"eval-{stamp}", "eval-latest"):
        (directory / f"{stem}.json").write_text(payload + "\n", encoding="utf-8")
        (directory / f"{stem}.md").write_text(text, encoding="utf-8")


def b1_execution_failed(report: EvaluationReport) -> bool:
    if any(point.b1.status not in {"NOT_RUN", "CALL_CAP", "REPLAY", "RECORDED"} for point in report.checkpoints):
        return True
    return report.previous_attempt is not None and b1_execution_failed(report.previous_attempt)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, default=ROOT / "fixtures/gold/dev/demo-story.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "docs/results")
    parser.add_argument("--limit-checkpoints", type=int)
    parser.add_argument("--mode", choices=("fallback", "replay"))
    parser.add_argument("--b1-mode", choices=("off", "replay", "record"), default="off")
    parser.add_argument("--max-calls", type=int, default=1, help="Total B1 call cap; candidate stays offline")
    args = parser.parse_args(argv)
    mode = args.mode or os.getenv("LLM_MODE", "replay")
    if mode not in {"fallback", "replay"}:
        parser.error("offline evaluation supports only fallback or replay")
    if args.limit_checkpoints is not None and args.limit_checkpoints < 1:
        parser.error("--limit-checkpoints must be positive")
    if args.max_calls < 0:
        parser.error("--max-calls must be nonnegative")
    raw = args.gold.read_bytes()
    gold = GoldFile.model_validate_json(raw)
    b1_session = B1Session(args.b1_mode, args.max_calls)
    report = run_evaluation(gold, hashlib.sha256(raw).hexdigest(), mode, args.limit_checkpoints, b1_session)
    if mode == "replay" and any("REPLAY_MISS" in point.stop_reasons for point in report.checkpoints):
        attempt = report
        report = run_evaluation(gold, attempt.gold_sha256, "fallback", args.limit_checkpoints, b1_session)
        report.requested_mode = "replay"
        report.fallback_reason = "REPLAY_MISS: matching recordings unavailable"
        report.previous_attempt = attempt
    write_report(report, args.output_dir)
    if isinstance(sys.stdout, TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    print(markdown(report))
    return int(b1_execution_failed(report) or any(point.error or point.stop_reasons or any(status not in {
        "COMPLETED", "WAITING_REVIEW", "WAITING_EVIDENCE"} for status in point.run_statuses)
        for point in report.checkpoints))


if __name__ == "__main__":
    raise SystemExit(main())
