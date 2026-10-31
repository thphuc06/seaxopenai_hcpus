"""Freeze and evaluate materialized blind sets without rewriting labels or first runs."""
from __future__ import annotations

import argparse
from collections.abc import Mapping
from contextlib import nullcontext
from datetime import datetime, timezone
import hashlib
from io import TextIOWrapper
import json
import os
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
from threading import Lock
from typing import Literal
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient
from pydantic import BaseModel, Field, JsonValue, model_validator

from app import config, seed
from app.budget import BudgetExceeded
from app.llm.client import network_guard
from app.models import AdmitResult, EventEnvelope, PUBLIC_FIELDS, PassportResponse, Verdict
from scripts import eval as evaluator
from scripts.check_fixtures import Product, Snapshot, check_fixtures
from scripts.sync_check import HEADERS, isolated_settings
from scripts.smoke import PriceBook, TokenUsage, request_bound


class BlindRecordBudget:
    """One pre-request reservation pool across every set, even if a run crashes."""
    def __init__(self, prices: PriceBook, models: set[str], max_calls: int) -> None:
        if not models or not models <= prices.models.keys():
            raise ValueError("Unknown active model price; record is not permitted")
        self.prices, self.models, self.max_calls = prices, models, max_calls
        self.calls = 0
        self.reserved_usd = 0.0
        self.aborted = False
        self.lock = Lock()

    @classmethod
    def from_settings(cls, max_calls: int) -> BlindRecordBudget:
        settings = config.settings
        if not settings.model_extract:
            raise ValueError("MODEL_EXTRACT must be configured for record")
        models = {value for value in (settings.model_extract, settings.model_cheap,
                                      settings.model_agent, settings.embed_model) if value}
        prices = PriceBook.model_validate_json((ROOT / "backend/app/data/model_prices.json").read_text(encoding="utf-8"))
        return cls(prices, models, max_calls)

    def reserve(self, request: Mapping[str, object]) -> None:
        with self.lock:
            if self.aborted:
                raise BudgetExceeded("RECORD_ACCOUNTING_UNKNOWN")
            if str(request.get("model")) not in self.models:
                raise BudgetExceeded("MODEL_PRICE_NOT_REVIEWED")
            messages = request.get("input", [])
            if isinstance(messages, list) and any(isinstance(message, dict) and any(
                    isinstance(part, dict) and part.get("type") == "input_image"
                    for part in message.get("content", [])) for message in messages):
                raise BudgetExceeded("VISION_TOKEN_COST_NOT_VERIFIED")
            bound = request_bound(request)
            if bound > 272_000 or request.get("tools"):
                raise BudgetExceeded("REQUEST_COST_NOT_VERIFIED")
            estimate = self.prices.cost(str(request["model"]), TokenUsage(input_tokens=bound,
                output_tokens=int(str(request["max_output_tokens"]))))
            if self.calls >= self.max_calls or self.reserved_usd + estimate > 3:
                raise BudgetExceeded("RECORD_SESSION_CAP")
            self.calls += 1
            self.reserved_usd += estimate

    def abort(self) -> None:
        with self.lock:
            self.aborted = True


class Evidence(BaseModel):
    file: str
    locator: str
    excerpt: str


class ClaimTarget(BaseModel):
    kind: str
    expected: Verdict
    rationale: str


class BlindCase(BaseModel):
    product_id: str
    case_id: str
    folder: str
    status: Literal["DRAFT", "REVIEWED"]
    reviewed_by: str | None = None
    expected: dict[str, Verdict]
    evidence: dict[str, list[Evidence]]
    rationale: dict[str, JsonValue]
    categories: list[str]
    probes: list[dict[str, JsonValue]]
    claims: list[ClaimTarget]
    unscored_claims: list[str] = Field(default_factory=list)
    unmet_preconditions: list[str] = Field(default_factory=list)
    no_seller_blame: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_labels(self) -> BlindCase:
        if set(self.expected) != set(PUBLIC_FIELDS):
            raise ValueError("Blind case must declare all five fields")
        if self.status == "REVIEWED" and (not self.reviewed_by or self.reviewed_by.startswith("draft:")):
            raise ValueError("REVIEWED requires a named human reviewer")
        if not set(self.unscored_claims) <= {claim.kind for claim in self.claims}:
            raise ValueError("Unscored claim must name an existing target")
        return self


class BlindSet(BaseModel):
    set_number: int
    original_plan: str
    labelled_by: str
    cases: list[BlindCase]
    deferred: list[dict[str, str]]
    limitations: list[str]

    @model_validator(mode="after")
    def unique_cases(self) -> BlindSet:
        for attribute in ("product_id", "case_id", "folder"):
            values = [getattr(case, attribute) for case in self.cases]
            if len(values) != len(set(values)):
                raise ValueError("Duplicate blind case identity")
        if not self.cases:
            raise ValueError("Blind set is empty")
        return self


class Freeze(BaseModel):
    set_number: int
    frozen_at: str
    hashes: dict[str, str]


class ClaimComparison(BaseModel):
    kind: str
    expected: Verdict
    actual: Verdict | None
    scored: bool


class BlindResult(BaseModel):
    product_id: str
    status: str
    reviewed_by: str | None
    outcome: str | None = None
    error: str | None = None
    fields: list[evaluator.FieldComparison] = Field(default_factory=list)
    scores: dict[str, evaluator.Score] = Field(default_factory=dict)
    claims: list[ClaimComparison] = Field(default_factory=list)
    claim_findings: list[dict[str, JsonValue]] = Field(default_factory=list)
    usage: evaluator.Usage = Field(default_factory=evaluator.Usage)
    stops: list[str] = Field(default_factory=list)
    probes: list[dict[str, JsonValue]]
    unmet_preconditions: list[str]


class BlindReport(BaseModel):
    set_number: int
    run_id: str
    generated_at: str
    mode: str
    attempt: str
    freeze: Freeze
    results: list[BlindResult]
    totals: dict[str, dict[str, evaluator.Score]]
    usage: evaluator.Usage
    limitations: list[str]
    accounting_complete: bool = True


def contained(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Manifest path escapes repository root")
    return path


def text_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def validate_inputs(root: Path, manifest_path: Path, dataset: BlindSet) -> dict[str, str]:
    """Format/evidence checks only; no candidate execution or predicted-label comparison."""
    paths = [manifest_path, contained(root, dataset.original_plan)]
    for case in dataset.cases:
        folder = contained(root, case.folder)
        product = Product.model_validate_json((folder / "product.json").read_text(encoding="utf-8"))
        if product.product_id != case.product_id or product.case_id != case.case_id:
            raise ValueError("Manifest/product identity mismatch")
        paths.extend(sorted(folder.glob("*.json")))
        for field, evidence in case.evidence.items():
            if field not in PUBLIC_FIELDS:
                raise ValueError("Unknown evidence field")
            for citation in evidence:
                source_path = contained(folder, citation.file)
                snapshot = Snapshot.model_validate_json(source_path.read_text(encoding="utf-8"))
                if not any(p.locator == citation.locator and citation.excerpt and
                           citation.excerpt in p.text for p in snapshot.passages):
                    raise ValueError("Expected evidence locator/excerpt is absent")
        if any(case.expected[field] != Verdict.INSUFFICIENT and not case.evidence.get(field) for field in PUBLIC_FIELDS):
            raise ValueError("Non-insufficient label needs an evidence anchor")
    return {path.relative_to(root).as_posix(): text_hash(path) for path in sorted(set(paths))}


def freeze_inputs(root: Path, manifest_path: Path, dataset: BlindSet, path: Path) -> Freeze:
    frozen = Freeze(set_number=dataset.set_number, frozen_at=datetime.now(timezone.utc).isoformat(),
                    hashes=validate_inputs(root, manifest_path, dataset))
    if path.exists():
        existing = Freeze.model_validate_json(path.read_text(encoding="utf-8"))
        if existing.set_number != frozen.set_number or existing.hashes != frozen.hashes:
            raise ValueError("Frozen inputs changed; retain original labels/first run and create an explicitly versioned set")
        return existing
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as output:
        output.write(frozen.model_dump_json(indent=2) + "\n")
    return frozen


def verify_freeze(root: Path, manifest: Path, dataset: BlindSet, path: Path) -> Freeze:
    frozen = Freeze.model_validate_json(path.read_text(encoding="utf-8"))
    if frozen.set_number != dataset.set_number or frozen.hashes != validate_inputs(root, manifest, dataset):
        raise ValueError("Frozen inputs changed; evaluation refused before pipeline execution")
    return frozen


def evaluate_case(client: TestClient, database: Path, case: BlindCase, remaining: int,
                  mode: str, root: Path) -> BlindResult:
    result = BlindResult(product_id=case.product_id, status=case.status, reviewed_by=case.reviewed_by,
        probes=case.probes, unmet_preconditions=case.unmet_preconditions)
    if mode != "fallback" and remaining <= 0:
        result.error = "SET_CALL_CAP"
        return result
    seed.load_product_dir(contained(root, case.folder))
    envelope = EventEnvelope.model_validate({"event_id": "blind-" + uuid4().hex, "type": "BOOTSTRAP", "producer": "publisher-panel",
        "idempotency_key": "blind-" + uuid4().hex, "occurred_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": "1", "resource": {"kind": "CASE", "id": case.case_id, "version": 1},
        "changed_fields": [], "correlation_id": "blind-evaluation",
        "payload": {"product_id": case.product_id, "case_id": case.case_id}})
    with patch.dict(os.environ, {"RUN_MAX_MODEL_CALLS": str(min(config.settings.run_max_model_calls, remaining))}):
        config.reload_settings()
        response = client.post("/api/internal/events", headers=HEADERS["OPERATOR"], json=envelope.model_dump(mode="json"))
    config.reload_settings()
    if not response.is_success:
        result.error = f"event HTTP {response.status_code}"
        return result
    result.outcome = AdmitResult.model_validate(response.json()).outcome.value
    if result.outcome != "ADMITTED":
        result.error = "event " + result.outcome
        return result
    response = client.get(f"/api/products/{case.product_id}/passport", headers=HEADERS["REVIEWER"])
    if not response.is_success:
        result.error = f"passport HTTP {response.status_code}"
        return result
    passport = PassportResponse.model_validate(response.json())
    actual = {field.field_key: field.verdict for field in passport.fields}
    stored = {str(row["field_key"]): row for row in evaluator.read_rows(database,
        "SELECT field_key,verdict,seller_attributable,review_state FROM field_results WHERE case_id=? AND superseded_by IS NULL", (case.case_id,))}
    b0 = {field.field_key: field for field in evaluator.stored_baseline(database, case.case_id)}
    for key, expected in case.expected.items():
        result.fields.append(evaluator.FieldComparison(field_key=key, expected=expected,
            b0=b0[key].verdict, b0_seller_attributable=b0[key].seller_attributable,
            candidate=actual.get(key), candidate_seller_attributable=bool(stored[key]["seller_attributable"]) if key in stored else None,
            expected_seller_attributable=False if key in case.no_seller_blame or expected != Verdict.CONFLICTING else None))
    result.scores = {name: evaluator.score_fields(result.fields, name) for name in ("B0", "candidate")}
    result.claim_findings = [row for key, row in stored.items() if key.startswith("claim:")]
    for target in case.claims:
        finding = stored.get("claim:" + target.kind)
        result.claims.append(ClaimComparison(kind=target.kind, expected=target.expected,
            actual=Verdict(str(finding["verdict"])) if finding else None, scored=target.kind not in case.unscored_claims))
    for row in evaluator.read_rows(database, "SELECT usage_json,status,stop_reason FROM runs WHERE case_id=?", (case.case_id,)):
        usage = evaluator.StoredUsage.model_validate_json(str(row["usage_json"] or "{}"))
        result.usage.add(evaluator.Usage(model_calls=int(usage.model_calls.used), tokens_in=usage.tokens.input_tokens,
            tokens_out=usage.tokens.output_tokens, latency_ms=usage.seconds.used * 1000))
        if row["stop_reason"]:
            result.stops.append(str(row["stop_reason"]))
        if row["status"] in {"FAILED", "PARTIAL", "QUEUED", "RUNNING"}:
            result.error = str(row["status"]) + ":" + str(row["stop_reason"])
    if result.error:
        result.scores = {}  # Retain raw and code-verified partial findings without scoring incomplete cases.
        for claim in result.claims:
            claim.scored = False
    return result


def run_set(dataset: BlindSet, frozen: Freeze, mode: str, max_calls: int, *, root: Path = ROOT,
            record_budget: BlindRecordBudget | None = None) -> BlindReport:
    from app.main import create_app
    results: list[BlindResult] = []
    usage = evaluator.Usage()
    accounting_complete = True
    if mode == "record" and max_calls > 0 and record_budget is None:
        record_budget = BlindRecordBudget.from_settings(max_calls)

    def deny_network(**request: object) -> None:
        raise RuntimeError("Offline blind evaluation attempted a provider call")

    with TemporaryDirectory(prefix="passport-blind-") as directory:
        database = Path(directory) / "blind.db"
        empty = Path(directory) / "empty-fixtures"
        empty.mkdir()
        with isolated_settings(mode, database, replay_freeze=False), patch.dict(os.environ, {"FIXTURES_DIR": str(empty)}), \
                (patch("app.llm.client._call_api", deny_network) if mode != "record" else nullcontext()), \
                (network_guard(record_budget.reserve) if record_budget is not None else nullcontext()):
            config.reload_settings()
            with TestClient(create_app()) as client:
                for case in dataset.cases:
                    try:
                        result = evaluate_case(client, database, case, max_calls - usage.model_calls, mode, root)
                    except (RuntimeError, ValueError, OSError, sqlite3.Error) as error:
                        result = BlindResult(product_id=case.product_id, status=case.status, reviewed_by=case.reviewed_by,
                            error=f"{type(error).__name__}: accounting unknown", probes=case.probes,
                            unmet_preconditions=case.unmet_preconditions)
                        results.append(result)
                        accounting_complete = False
                        if record_budget is not None:
                            record_budget.abort()
                        break  # Preserve partial results; never continue with unknown call accounting.
                    results.append(result)
                    usage.add(result.usage)
    totals = {status: {system: evaluator.Score() for system in ("B0", "candidate")} for status in ("DRAFT", "REVIEWED")}
    for result in results:
        for system, score in result.scores.items():
            totals[result.status][system].add(score)
    return BlindReport(set_number=dataset.set_number, run_id=uuid4().hex,
        generated_at=datetime.now(timezone.utc).isoformat(), mode=mode.upper(), attempt="UNASSIGNED",
        freeze=frozen, results=results, totals=totals, usage=usage, limitations=dataset.limitations,
        accounting_complete=accounting_complete)


def markdown(report: BlindReport) -> str:
    lines = [f"# Blind set {report.set_number} — {report.attempt}", "",
        f"Run: {report.run_id}; {report.generated_at}; mode {report.mode}",
        "Codex-assisted DRAFT labels are preliminary diagnostics; human-reviewed scores are separate.",
        "Incomplete cases retain raw findings but are excluded from successful accuracy and abstention totals.",
        f"Call accounting complete: {report.accounting_complete}", "",
        "| Gold | System | Correct/total | False seller blame/eligible | Abstentions |", "|---|---|---:|---:|---:|"]
    for status, systems in report.totals.items():
        for name, score in systems.items():
            lines.append(f"| {status} | {name} | {score.correct}/{score.total} | {score.false_blame}/{score.false_blame_eligible} | {score.abstentions} |")
    lines += ["", "| Product | Gold / reviewer | Field | Expected | Got | B0 |", "|---|---|---|---|---|---|"]
    for result in report.results:
        for field in result.fields:
            lines.append(f"| {result.product_id} | {result.status} / {result.reviewed_by or 'pending'} | {field.field_key} | {field.expected} | {field.candidate or 'MISSING'} | {field.b0} |")
    lines += ["", "## Probes, claims and execution", ""]
    for result in report.results:
        lines.append(f"- {result.product_id}: {result.usage.model_calls} calls, {result.usage.tokens_in}/{result.usage.tokens_out} tokens; error={result.error or 'none'}; stops={','.join(result.stops) or 'none'}.")
        for field in result.fields:
            if field.candidate != field.expected:
                lines.append(f"  - MISS {field.field_key}: {field.expected} → {field.candidate or 'MISSING'}; probes={json.dumps(result.probes, ensure_ascii=False)}")
        for target in result.claims:
            lines.append(f"  - claim:{target.kind}: expected {target.expected}, got {target.actual or 'MISSING'}; {'scored' if target.scored else 'UNSCORED precondition' }.")
        for condition in result.unmet_preconditions:
            lines.append("  - Precondition: " + condition)
    lines += ["", "## Limitations", ""] + ["- " + item for item in report.limitations]
    return "\n".join(lines) + "\n"


def write_report(report: BlindReport, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    first = directory / f"blind-set{report.set_number}.json"
    report.attempt = "FIRST_RUN" if not first.exists() else "RERUN"
    stem = f"blind-set{report.set_number}" if report.attempt == "FIRST_RUN" else f"blind-set{report.set_number}-rerun-{report.run_id}"
    # Exclusive creation keeps the first report even across concurrent attempts.
    with (directory / (stem + ".json")).open("x", encoding="utf-8") as output:
        output.write(report.model_dump_json(indent=2) + "\n")
    with (directory / (stem + ".md")).open("x", encoding="utf-8") as output:
        output.write(markdown(report))
    summary = ["# Blind first-run summary", "", "First results only. Reruns are separate; DRAFT is not reviewed accuracy.", ""]
    for path in sorted(directory.glob("blind-set*.json")):
        if "-rerun-" in path.stem:
            continue
        stored = BlindReport.model_validate_json(path.read_text(encoding="utf-8"))
        for status in ("DRAFT", "REVIEWED"):
            score = stored.totals[status]["candidate"]
            summary.append(f"- Set {stored.set_number}, {stored.mode}, {status}: {score.correct}/{score.total}; false blame {score.false_blame}/{score.false_blame_eligible}; run {stored.run_id}.")
    (directory / "blind-summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set", default="1")
    parser.add_argument("--mode", choices=("fallback", "replay", "record"), default="fallback")
    parser.add_argument("--max-calls", type=int, default=60)
    parser.add_argument("--freeze", action="store_true", help="Validate and freeze only; never execute a candidate")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "docs/results")
    args = parser.parse_args(argv)
    if args.max_calls < 0 or (args.set != "all" and (not args.set.isdigit() or int(args.set) < 1)):
        parser.error("select a positive set number/all and a nonnegative call cap")
    if isinstance(sys.stdout, TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    manifests = sorted((ROOT / "fixtures/gold/blind").glob("materialized-set*.json")) if args.set == "all" else [
        ROOT / f"fixtures/gold/blind/materialized-set{args.set}.json"]
    if not manifests:
        parser.error("no materialized sets found")
    remaining = args.max_calls
    record_bound = 0.0
    failed = False
    try:
        record_budget = BlindRecordBudget.from_settings(remaining) if args.mode == "record" and not args.freeze else None
        for manifest in manifests:
            dataset = BlindSet.model_validate_json(manifest.read_text(encoding="utf-8"))
            freeze_path = ROOT / f"docs/results/blind-freeze-set{dataset.set_number}.json"
            if args.freeze:
                invalid = [check for check in check_fixtures(ROOT / "fixtures") if check.problems]
                if invalid:
                    raise ValueError("Fixture validation failed: " + "; ".join(str(check.path) for check in invalid))
                frozen = freeze_inputs(ROOT, manifest, dataset, freeze_path)
                print(f"Frozen set {dataset.set_number}: {len(dataset.cases)} cases, {len(frozen.hashes)} files; no candidate execution")
                continue
            frozen = verify_freeze(ROOT, manifest, dataset, freeze_path)
            if args.mode == "record":
                assert record_budget is not None
                rates = [record_budget.prices.models[model] for model in record_budget.models]
                source_bytes = sum(contained(ROOT, name).stat().st_size for name in frozen.hashes)
                estimate = remaining * ((source_bytes + 16384) * max(rate.input_per_million for rate in rates) +
                    config.settings.llm_max_output_tokens * max(rate.output_per_million for rate in rates)) / 1_000_000
                print(f"Record conservative estimate ${estimate:.4f}, cap {remaining} calls", flush=True)
                if record_bound + estimate > 3:
                    raise ValueError("Estimate exceeds $3; lower --max-calls or request human approval before recording")
                record_bound += estimate
            report = run_set(dataset, frozen, args.mode, remaining, record_budget=record_budget)
            remaining -= report.usage.model_calls
            write_report(report, args.output_dir)
            print(markdown(report))
            failed |= any(result.error for result in report.results)
            if not report.accounting_complete:
                failed = True
                break
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Blind evaluation error: {error}", file=sys.stderr)
        return 1
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
