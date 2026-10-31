"""Single-listing diagnostic or Phase-2 bootstrap record pass; dry by default.

--events uses an isolated database, shared 30-call / USD 2 ledger and exact-ID
replay. --execute belongs in the human terminal. No expected labels are generated.
"""
from __future__ import annotations

import argparse
from collections.abc import Mapping
from contextlib import closing, contextmanager
from dataclasses import replace
import hashlib
import json
import os
import sqlite3
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Lock
from typing import Iterator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from pydantic import BaseModel, ConfigDict, Field

from app import config, db, seed, store, worker
from app.budget import Budget, BudgetExceeded
from app.context import RunContext
from app.llm.client import LLMError, network_guard
from app.llm.messages import build_input
from app.models import ClaimExtraction, EventEnvelope, Role
from app.events.admit import admit
from app.pipeline.extract import CACHE_VERSION, INSTRUCTIONS, PROMPT_VERSION, RETRY_VERSION, Extraction, extract_source_version, extraction_input
from app.pipeline.fallback_extract import FALLBACK_VERSION, Passage
from app.trace import TraceWriter
from scripts.smoke import LedgerState, PriceBook, SmokeFailure, TokenUsage, request_bound


class CheckpointError(RuntimeError):
    """A diagnostic code, never a provider payload."""


class Stage(BaseModel):
    mode: str
    extractor: str
    claims: int
    model_calls: int
    tokens: TokenUsage
    estimated_usd: float
    values: list[str]


class Report(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fingerprint: str
    model: str
    prompt_version: str
    estimated_upper_usd: float
    network_call_cap: int = 2
    cost_cap_usd: float = 0.50
    stages: list[Stage] = Field(default_factory=list)
    replay_equal: bool | None = None
    fallback_equal: bool | None = None


@contextmanager
def isolated_settings(folder: Path) -> Iterator[None]:
    previous = config.settings
    config.settings = replace(previous, db_path=folder / "checkpoint.db", replay_dir=folder / "replay", ocr_enabled=False)
    try:
        yield
    finally:
        config.settings = previous


def prepare(snapshot: dict[str, db.JSON]) -> tuple[str, list[Passage]]:
    db.init_db()
    product = str(snapshot["product_id"])
    with db.transaction() as connection:
        connection.execute("INSERT INTO products(id,dataset_origin) VALUES(?,?)", (product, snapshot["dataset_origin"]))
        connection.execute("INSERT INTO cases(id,product_id,tenant_id,revision) VALUES('checkpoint',?,'operator',0)", (product,))
        ref = store.ingest(connection, snapshot, case_id="checkpoint", origin=str(snapshot["dataset_origin"]))
        rows = connection.execute("SELECT * FROM passages WHERE source_version_id=? ORDER BY rowid", (ref.id,)).fetchall()
    return ref.id, [Passage.model_validate(dict(row)) for row in rows]


def values(result: Extraction) -> list[str]:
    """Compare canonical observations, excluding ids and mode-specific provenance."""
    return sorted({json.dumps([claim.field_key, {key: value for key, value in claim.normalized.items() if key != "items"}, claim.readability.value], sort_keys=True, ensure_ascii=False)
                   for claim in result.claims})


def run_stage(mode: str, sv_id: str, product_id: str, prices: PriceBook) -> Stage:
    # Independent diagnostic runs, each with its own run budget and persisted trace.
    with db.transaction() as connection:
        connection.execute("INSERT INTO runs(id,case_id,llm_mode,started_at) VALUES(?,'checkpoint',?,?)", (mode, mode, db.now_iso()))
    budget = Budget(max_model_calls=2 if mode in {"record", "replay"} else 0, max_tool_calls=0)
    ctx = RunContext(mode, "checkpoint", "operator", 0, {"id": product_id}, mode, budget, TraceWriter(mode))
    result = extract_source_version(sv_id, ctx)
    with db.transaction() as connection:
        check_step_errors(connection, run_id=mode)
    usage = TokenUsage.model_validate(budget.usage()["tokens"])
    return Stage(mode=mode, extractor=result.extractor, claims=len(result.claims), model_calls=budget.model_calls,
                 tokens=usage, estimated_usd=prices.cost(config.settings.model_extract, usage), values=values(result))


def checkpoint(snapshot_path: Path, output_dir: Path, *, execute: bool = False) -> Report:
    snapshot = db.loads(snapshot_path.read_text(encoding="utf-8"))
    if not isinstance(snapshot, dict) or snapshot.get("kind") != "LISTING" or snapshot.get("dataset_origin") not in {"REAL", "SYNTHETIC"}:
        raise CheckpointError("EXPECTED_LISTING_SNAPSHOT")
    settings = config.settings
    if not settings.model_extract:
        raise CheckpointError("MODEL_EXTRACT_NOT_CONFIGURED")
    if settings.replay_freeze:
        raise CheckpointError("REPLAY_FREEZE_ENABLED")
    prices = PriceBook.model_validate_json((ROOT / "backend/app/data/model_prices.json").read_text(encoding="utf-8"))
    identity = [snapshot, settings.model_extract, settings.llm_effort_extract, settings.llm_max_output_tokens,
                PROMPT_VERSION, INSTRUCTIONS, ClaimExtraction.model_json_schema(), FALLBACK_VERSION, CACHE_VERSION, RETRY_VERSION]
    fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    report_path = output_dir / "report.json"
    if execute and report_path.exists():
        report = Report.model_validate_json(report_path.read_text(encoding="utf-8"))
        if report.fingerprint != fingerprint:
            raise CheckpointError("OUTPUT_IDENTITY_CHANGED")
        return report  # Completed diagnostic: no new call or overwritten recording.
    if execute and output_dir.exists():
        raise CheckpointError("OUTPUT_EXISTS_USE_NEW_DIRECTORY")
    with TemporaryDirectory(prefix="p2-estimate-") as temporary:
        with isolated_settings(Path(temporary)):
            sv_id, passages = prepare(snapshot)
            request = {"model": settings.model_extract, "input": build_input(INSTRUCTIONS, extraction_input(sv_id, passages)),
                       "text_format": ClaimExtraction, "reasoning": {"effort": settings.llm_effort_extract},
                       "max_output_tokens": settings.llm_max_output_tokens}
            upper = 2 * prices.cost(settings.model_extract, TokenUsage(input_tokens=request_bound(request), output_tokens=settings.llm_max_output_tokens))
    report = Report(fingerprint=fingerprint, model=settings.model_extract, prompt_version=PROMPT_VERSION, estimated_upper_usd=upper)
    print(f"Estimate <= ${upper:.6f}; cap $0.50; at most 2 network requests including retry.", flush=True)
    if upper > report.cost_cap_usd:
        raise CheckpointError("ESTIMATE_EXCEEDS_CAP")
    if not execute:
        return report
    if not settings.openai_api_key:
        raise CheckpointError("MISSING_BACKEND_KEY")
    # mkdir is exclusive: an interrupted/failed attempt cannot silently reset its
    # spending allowance. Preserve the directory and choose a new one explicitly.
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "attempt.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    with isolated_settings(output_dir):
        sv_id, _ = prepare(snapshot)
        for mode in ("record", "replay", "fallback"):
            report.stages.append(run_stage(mode, sv_id, str(snapshot["product_id"]), prices))
        recorded, replayed, fallback = report.stages
        report.replay_equal = recorded.values == replayed.values
        report.fallback_equal = recorded.values == fallback.values
        if replayed.extractor != "REPLAY" or replayed.tokens.input_tokens or replayed.tokens.output_tokens or not report.replay_equal:
            raise CheckpointError("REPLAY_VERIFICATION_FAILED")
        if not recorded.claims:
            raise CheckpointError("NO_VALIDATED_CLAIMS")
    report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return report


class PassReport(BaseModel):
    network_call_cap: int = 30
    cost_cap_usd: float = 2.0
    events: list[str]
    source_count: int
    call_arithmetic: str
    calls: int = 0
    reserved_usd: float = 0
    replay_equal: bool | None = None
    replay_tokens: int = 0
    pending_checks: list[str] = Field(default_factory=list)


class PassLedger:
    """Persist worst-case reservations before each attempt, including retries."""
    def __init__(self, path: Path, prices: PriceBook) -> None:
        self.path, self.prices = path, prices
        self.state = LedgerState()
        self._lock = Lock()
        if path.exists():
            lines = path.read_text(encoding="utf-8").splitlines()
            if not lines:
                raise CheckpointError("INCOMPLETE_SPEND_LEDGER")
            for line in lines:
                row = LedgerState.model_validate_json(line)
                if row.calls != self.state.calls + 1 or not self.state.committed_usd <= row.committed_usd <= 2.0 or row.calls > 30:
                    raise CheckpointError("INVALID_SPEND_LEDGER")
                self.state = row

    def reserve(self, request: Mapping[str, object]) -> None:
        with self._lock:
            self._reserve(request)

    def _reserve(self, request: Mapping[str, object]) -> None:
        # Encoded PNG byte length is not a bound on vision token use. Fail
        # closed until this model's image accounting is independently verified.
        messages = request.get("input", [])
        if isinstance(messages, list) and any(isinstance(message, dict) and any(
            isinstance(part, dict) and part.get("type") == "input_image" for part in message.get("content", [])
        ) for message in messages):
            raise BudgetExceeded("VISION_TOKEN_COST_NOT_VERIFIED")
        estimate = self.prices.cost(str(request["model"]), TokenUsage(
            input_tokens=request_bound(request), output_tokens=int(str(request["max_output_tokens"]))))
        if self.state.calls >= 30 or self.state.committed_usd + estimate > 2.0:
            raise BudgetExceeded("RECORD_PASS_CAP")
        next_state = LedgerState(calls=self.state.calls + 1, committed_usd=self.state.committed_usd + estimate)
        # Append and fsync before sending. An interrupted row fails closed on
        # reload; no repeated Windows replace of a scanned/open destination.
        with self.path.open("a", encoding="utf-8") as journal:
            journal.write(next_state.model_dump_json() + "\n")
            journal.flush()
            os.fsync(journal.fileno())
        self.state = next_state


def check_step_errors(connection: sqlite3.Connection, *, run_id: str | None = None) -> None:
    row = connection.execute(
        "SELECT 1 FROM trace_steps WHERE (? IS NULL OR run_id=?) AND (error IS NOT NULL OR "
        "json_extract(detail,'$.stop_reason') IS NOT NULL AND json_extract(detail,'$.stop_reason')!='NO_CLAIM_CUES')",
        (run_id, run_id)).fetchone()
    if row:
        raise CheckpointError("STEP_INCOMPLETE_INSPECT_TRACE")


def copy_database(source: Path, destination: Path) -> None:
    """SQLite backup preserves every model-visible ID, including WAL contents."""
    if destination.exists():
        raise CheckpointError("DATABASE_DESTINATION_EXISTS")
    with closing(sqlite3.connect(source)) as original, closing(sqlite3.connect(destination)) as target:
        original.backup(target)


@contextmanager
def pass_settings(folder: Path, mode: str) -> Iterator[None]:
    previous = config.settings
    config.settings = replace(previous, db_path=folder / (mode + ".db"), replay_dir=folder / "replay",
        llm_mode="fallback" if mode == "base" else mode, replay_freeze=mode == "replay", ocr_enabled=False, demo_run_delay_s=0,
        worker_inline=True, web_search="off")
    try:
        yield
    finally:
        config.settings = previous


def pass_results(events: list[EventEnvelope]) -> tuple[list[str], int]:
    for event in events:
        result = admit(event, role=Role.OPERATOR, actor_id="record-pass-operator")
        if result.outcome != "ADMITTED" or not result.job_id:
            raise CheckpointError("BOOTSTRAP_NOT_ADMITTED")
        worker.execute_job(result.job_id)
    with db.transaction() as connection:
        if connection.execute("SELECT 1 FROM runs WHERE stop_reason IS NOT NULL OR error IS NOT NULL OR status IN ('FAILED','PARTIAL')").fetchone():
            raise CheckpointError("RUN_INCOMPLETE_INSPECT_TRACE")
        check_step_errors(connection)
        fields = [json.dumps(dict(row), sort_keys=True, ensure_ascii=False) for row in connection.execute(
            "SELECT case_id,field_key,verdict,review_state,freshness,public_text,citations_json,depends_on_json "
            "FROM field_results WHERE superseded_by IS NULL ORDER BY case_id,field_key")]
        tokens = connection.execute("SELECT COALESCE(SUM(tokens_in+tokens_out),0) FROM trace_steps WHERE actor='llm'").fetchone()[0]
    if not fields:
        raise CheckpointError("NO_PUBLISHED_FIELDS")
    return fields, tokens


def record_pass(event_paths: list[Path], output_dir: Path, *, execute: bool = False, replay_only: bool = False) -> PassReport:
    """Bootstrap only. Event 10 belongs to the separate post-S2 recording pass."""
    events: list[EventEnvelope] = []
    for path in event_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.pop("expect", None)  # Fixture annotation is not an event-envelope field.
        events.append(EventEnvelope.model_validate(payload))
    if not events or any(event.type != "BOOTSTRAP" for event in events):
        raise CheckpointError("PASS_ONE_REQUIRES_BOOTSTRAP_EVENTS")
    if len({event.resource.id for event in events}) != len(events):
        raise CheckpointError("DUPLICATE_BOOTSTRAP_CASE")
    print("Record pass 1: cap <=30 network calls / <=$2 total, including failed requests and retries. No web calls.", flush=True)
    prices = PriceBook.model_validate_json((ROOT / "backend/app/data/model_prices.json").read_text(encoding="utf-8"))
    for model in {config.settings.model_extract, config.settings.model_cheap or config.settings.model_extract}:
        prices.cost(model, TokenUsage())
    if replay_only:
        report = PassReport.model_validate_json((output_dir / "pass-report.json").read_text(encoding="utf-8"))
        saved = json.loads((output_dir / "events.json").read_text(encoding="utf-8"))
        if saved != [event.model_dump(mode="json") for event in events]:
            raise CheckpointError("EVENT_IDENTITY_CHANGED")
        # A fresh temporary copy avoids replay extraction caches masking misses.
        with TemporaryDirectory(prefix="p2-pass-replay-") as temporary:
            folder = Path(temporary)
            copy_database(output_dir / "base.db", folder / "replay.db")
            with pass_settings(folder, "replay"):
                config.settings = replace(config.settings, replay_dir=output_dir / "replay")
                replayed, tokens = pass_results(events)
        expected = json.loads((output_dir / "record-results.json").read_text(encoding="utf-8"))
        report.replay_equal, report.replay_tokens = replayed == expected, tokens
        if not report.replay_equal or tokens:
            raise CheckpointError("REPLAY_VERIFICATION_FAILED")
        return report
    if execute and (config.settings.replay_freeze or not config.settings.openai_api_key):
        raise CheckpointError("RECORD_REQUIRES_UNFROZEN_BACKEND_KEY")
    if execute and output_dir.exists():
        raise CheckpointError("OUTPUT_EXISTS_USE_NEW_DIRECTORY")
    with TemporaryDirectory(prefix="p2-pass-prepare-") as temporary:
        prepared = Path(temporary)
        with pass_settings(prepared, "base"):
            seed.reset()
            with db.transaction() as connection:
                source_count = 0
                has_images = False
                for event in events:
                    if not connection.execute("SELECT 1 FROM cases WHERE id=?", (event.resource.id,)).fetchone():
                        raise CheckpointError("BOOTSTRAP_CASE_NOT_SEEDED")
                    source_count += connection.execute("SELECT COUNT(*) FROM sources WHERE case_id=?", (event.resource.id,)).fetchone()[0]
                    has_images |= bool(connection.execute("SELECT 1 FROM sources s JOIN source_versions v ON s.id=v.source_id WHERE s.case_id=? AND s.kind='PACKAGING_IMAGE' AND v.raw_path IS NOT NULL AND v.is_current=1", (event.resource.id,)).fetchone())
            report = PassReport(events=[event.event_id for event in events], source_count=source_count,
                call_arithmetic=f"{source_count} extract + <= {source_count} coverage retry + <= {len(events)} canon + <= {len(events)} claims; HTTP retries also consume the shared 30-call cap")
            if has_images and config.settings.llm_vision:
                report.pending_checks.append("VISION_TOKEN_COST_NOT_VERIFIED")
        if not execute:
            return report
        if report.pending_checks:
            raise CheckpointError("VISION_TOKEN_COST_NOT_VERIFIED")
        output_dir.mkdir(parents=True, exist_ok=False)
        (output_dir / "attempt.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
        (output_dir / "events.json").write_text(json.dumps([e.model_dump(mode="json") for e in events], ensure_ascii=False, indent=2), encoding="utf-8")
        copy_database(prepared / "base.db", output_dir / "base.db")
    copy_database(output_dir / "base.db", output_dir / "record.db")
    ledger = PassLedger(output_dir / "ledger.jsonl", prices)
    with pass_settings(output_dir, "record"), network_guard(ledger.reserve):
        recorded, _ = pass_results(events)
    (output_dir / "record-results.json").write_text(json.dumps(recorded, ensure_ascii=False, indent=2), encoding="utf-8")
    copy_database(output_dir / "base.db", output_dir / "replay.db")
    with pass_settings(output_dir, "replay"):
        replayed, tokens = pass_results(events)
    report.calls, report.reserved_usd = ledger.state.calls, ledger.state.committed_usd
    report.replay_equal, report.replay_tokens = recorded == replayed, tokens
    if not report.replay_equal or tokens:
        raise CheckpointError("REPLAY_VERIFICATION_FAILED")
    (output_dir / "pass-report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path, nargs="?", help="One LISTING snapshot JSON; no gold labels")
    parser.add_argument("--events", type=Path, nargs="+", help="Phase-2 bootstrap events; dry by default")
    parser.add_argument("--replay-only", action="store_true", help="Recheck a saved pass using its identical base database")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "backend/.venv/p2-record-checkpoint")
    parser.add_argument("--execute", action="store_true", help="Human terminal only: allow capped record, then replay and fallback")
    args = parser.parse_args()
    try:
        if args.events:
            if args.snapshot or (args.execute and args.replay_only):
                raise CheckpointError("INCOMPATIBLE_OPTIONS")
            report = record_pass([p.resolve() for p in args.events], args.output_dir.resolve(), execute=args.execute, replay_only=args.replay_only)
        elif args.snapshot and not args.replay_only:
            report = checkpoint(args.snapshot.resolve(), args.output_dir.resolve(), execute=args.execute)
        else:
            raise CheckpointError("SNAPSHOT_OR_EVENTS_REQUIRED")
    except (CheckpointError, SmokeFailure, LLMError, BudgetExceeded, OSError, ValueError, KeyError) as error:
        # Whitelisted domain errors contain only our codes; other errors may
        # contain source text or provider details and are reduced to type names.
        detail = str(error) if isinstance(error, (CheckpointError, SmokeFailure, LLMError, BudgetExceeded)) else type(error).__name__
        print(f"Checkpoint failed: {detail}. Existing attempt directory is retained.", file=sys.stderr)
        return 1
    # Keep report.json UTF-8; terminal output must also work on Windows cp1252.
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
