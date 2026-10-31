"""Plan a story, single-listing diagnostic or Phase-2 pass; dry by default.

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
import math
import os
import re
import sqlite3
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Lock
from typing import Iterator, Literal

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


def validate_caps(max_calls: int, max_usd: float) -> None:
    if isinstance(max_calls, bool) or not isinstance(max_calls, int) or max_calls <= 0 or not math.isfinite(max_usd) or max_usd <= 0:
        raise CheckpointError("FINITE_POSITIVE_CAPS_REQUIRED")


class PassLedger:
    """Persist worst-case reservations before each attempt, including retries."""
    def __init__(self, path: Path, prices: PriceBook, *, max_calls: int = 30, max_usd: float = 2.0) -> None:
        validate_caps(max_calls, max_usd)
        self.path, self.prices = path, prices
        self.max_calls, self.max_usd = max_calls, max_usd
        self.state = LedgerState()
        self._lock = Lock()
        if path.exists():
            lines = path.read_text(encoding="utf-8").splitlines()
            if not lines:
                raise CheckpointError("INCOMPLETE_SPEND_LEDGER")
            for line in lines:
                row = LedgerState.model_validate_json(line)
                if row.calls != self.state.calls + 1 or not self.state.committed_usd <= row.committed_usd <= max_usd or row.calls > max_calls:
                    raise CheckpointError("INVALID_SPEND_LEDGER")
                self.state = row

    def reserve(self, request: Mapping[str, object]) -> None:
        with self._lock:
            self._reserve(request)

    def _reserve(self, request: Mapping[str, object]) -> None:
        if "kind" in request:
            from app.connectors.websearch import MAX_BYTES, normalized_url
            if (set(request) != {"kind", "provider", "method", "url", "max_bytes"}
                    or request["kind"] != "web_fetch" or request["provider"] != "httpx"
                    or request["method"] != "GET" or request["max_bytes"] != MAX_BYTES
                    or not isinstance(request["url"], str)):
                raise BudgetExceeded("REQUEST_COST_NOT_VERIFIED")
            normalized_url(request["url"])
            # Direct HTTP GET has no model/provider fee, but consumes an attempt.
            self._commit_reservation(0.0)
            return
        # Encoded PNG byte length is not a bound on vision token use. Fail
        # closed until this model's image accounting is independently verified.
        messages = request.get("input", [])
        if isinstance(messages, list) and any(isinstance(message, dict) and any(
            isinstance(part, dict) and part.get("type") == "input_image" for part in message.get("content", [])
        ) for message in messages):
            raise BudgetExceeded("VISION_TOKEN_COST_NOT_VERIFIED")
        tools = request.get("tools")
        searches = 0
        if tools:
            if (not isinstance(tools, list) or len(tools) != 1 or not isinstance(tools[0], dict)
                    or tools[0].get("type") != "web_search"
                    or set(tools[0]) - {"type", "filters", "user_location", "search_context_size", "external_web_access"}
                    or type(request.get("max_tool_calls")) is not int or request["max_tool_calls"] != 1
                    or request.get("tool_choice") != {"type": "web_search"}
                    or request.get("service_tier") != "default"):
                raise BudgetExceeded("REQUEST_COST_NOT_VERIFIED")
            searches = 1
        bound = request_bound(request, web_tokens=self.prices.tools.search_context_token_limit if searches else 0)
        if bound > 272_000:
            raise BudgetExceeded("REQUEST_COST_NOT_VERIFIED")
        estimate = self.prices.cost(str(request["model"]), TokenUsage(
            input_tokens=bound, output_tokens=int(str(request["max_output_tokens"]))), searches=searches)
        self._commit_reservation(estimate)

    def _commit_reservation(self, estimate: float) -> None:
        if self.state.calls >= self.max_calls or self.state.committed_usd + estimate > self.max_usd:
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
def pass_settings(folder: Path, mode: str, *, web: Literal["off", "on"] = "off") -> Iterator[None]:
    previous = config.settings
    config.settings = replace(previous, db_path=folder / (mode + ".db"), replay_dir=folder / "replay",
        llm_mode="fallback" if mode == "base" else mode, replay_freeze=mode == "replay", ocr_enabled=False, demo_run_delay_s=0,
        worker_inline=True, web_search=web)
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


class StoryItem(BaseModel):
    name: str
    event: EventEnvelope
    product_dir: Path | None = None


class StoryPlan(BaseModel):
    fixtures_dir: Path
    items: list[StoryItem] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    input_hashes: dict[str, str] = Field(default_factory=dict)
    max_calls: int
    max_usd: float
    web: Literal["off", "on"] = "off"
    estimated_calls_upper: int = 0
    estimated_usd_upper: float | None = None
    fingerprint: str = ""


class StoryReceipt(BaseModel):
    name: str
    mode: str
    admission: str
    admission_reason: str = ""
    status: str
    run_status: str | None = None
    model_calls: int = 0
    stop_reasons: list[str] = Field(default_factory=list)


class StoryReport(BaseModel):
    plan: StoryPlan
    dry_run: bool = True
    network_calls: int = 0
    reserved_usd: float = 0
    receipts: list[StoryReceipt] = Field(default_factory=list)
    not_recorded: list[str] = Field(default_factory=list)
    fallback: list[str] = Field(default_factory=list)
    replay_equal: bool | None = None
    complete: bool = False


def _read_event(path: Path) -> EventEnvelope:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.pop("expect", None)
    return EventEnvelope.model_validate(payload)


def _story_order(storyboard: Path, events: list[Path], missing: list[str]) -> list[Path]:
    """Use action cells only; prose elsewhere does not schedule extra events."""
    if not storyboard.is_file():
        return events
    ordered: list[Path] = []
    for line in storyboard.read_text(encoding="utf-8").splitlines():
        cells = line.split("|")
        if len(cells) < 4 or not re.match(r"\s*\d+\s*[·.]", cells[1]):
            continue
        for match in re.finditer(r"\bevent(?:-btn-)?(\d{2})(-[a-z0-9-]+)?\b", cells[2]):
            number, suffix = match.groups()
            candidates = [p for p in events if p.stem == number + suffix] if suffix else [p for p in events if p.stem.startswith(number + "-")]
            if len(candidates) != 1:
                missing.append("storyboard:event" + number + (suffix or ""))
            elif candidates[0] not in ordered:
                ordered.append(candidates[0])
    return ordered + [path for path in events if path not in ordered]


def _source_hashes(root: Path) -> dict[str, str]:
    # No gold directory traversal; only source metadata and image inputs.
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for group in ("synthetic", "real", "uploads", "blind/set1")
            for path in (root / group).rglob("*")
            if path.is_file() and path.suffix in {".json", ".png", ".jpg"}}


def story_plan(*, fixtures_dir: Path | None = None, storyboard: Path | None = None,
               max_calls: int = 30, max_usd: float = 2.0, web: Literal["off", "on"] = "off") -> StoryPlan:
    """Read event/source metadata only. No gold, pipeline runs or provider calls."""
    validate_caps(max_calls, max_usd)
    root = (fixtures_dir or config.settings.fixtures_dir).resolve()
    board = storyboard or ROOT / "scripts/demo/storyboard.md"
    plan = StoryPlan(fixtures_dir=root, max_calls=max_calls, max_usd=max_usd, web=web)
    events = sorted((root / "events").glob("*.json"))
    if not events:
        plan.missing_inputs.append("events/*.json")
    if not board.is_file():
        plan.notes.append("STORYBOARD_MISSING: using numbered event order")
    ordered = _story_order(board, events, plan.missing_inputs)
    # The repository contract enumerates 01..17; this detects absent event files,
    # independently of their product names, payloads or expected results.
    for number in range(1, 18):
        if not any(path.stem.startswith(f"{number:02}-") for path in events):
            plan.missing_inputs.append(f"events/{number:02}-*.json")
    seen: dict[str, EventEnvelope] = {}
    for path in ordered:
        event = _read_event(path)
        if event.event_id in seen:
            if seen[event.event_id] != event:
                plan.blockers.append("DUPLICATE_EVENT_ID_CONFLICT:" + event.event_id)
            continue
        seen[event.event_id] = event
        plan.items.append(StoryItem(name=path.stem, event=event))
    products = sorted((root / "blind/set1").glob("*/product.json"))
    if not products:
        plan.missing_inputs.append("blind/set1/*/product.json")
    for path in products:
        product = seed.read_object(path)
        case_id = str(product["case_id"])
        identity = hashlib.sha256((str(product["product_id"]) + ":" + case_id).encode("utf-8")).hexdigest()
        event = EventEnvelope.model_validate({"event_id": "record-blind-" + identity, "idempotency_key": "record-blind:" + identity,
            "type": "BOOTSTRAP", "schema_version": "1", "producer": "publisher-panel",
            "resource": {"kind": "CASE", "id": case_id, "version": 1}, "changed_fields": [],
            "payload": {"case_id": case_id}, "occurred_at": "2026-10-31T00:00:00Z", "correlation_id": "record-blind-set1"})
        existing = next((item for item in plan.items if item.event.type == "BOOTSTRAP" and item.event.resource.id == case_id), None)
        if existing is not None:
            existing.product_dir = path.parent
            continue
        plan.items.append(StoryItem(name="blind/set1/" + path.parent.name, event=event, product_dir=path.parent))
    # Freeze only source inputs, never labels. Include later-version snapshots and
    # image bytes because events may ingest them after the base database is saved.
    plan.input_hashes = _source_hashes(root)
    for item in plan.items:
        snapshot = item.event.payload.get("snapshot")
        if snapshot:
            path = (root / str(snapshot)).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                plan.missing_inputs.append(item.name + ":snapshot:" + str(snapshot))
    product_paths = [path for group in ("synthetic", "real", "blind/set1")
                     for path in (root / group).rglob("product.json")]
    for path in product_paths:
        if not list(path.parent.glob("*.v1.json")):
            plan.missing_inputs.append(path.parent.relative_to(root).as_posix() + ":sources")
    available_cases = {str(seed.read_object(path).get("case_id")) for path in product_paths}
    for item in plan.items:
        case = item.event.payload.get("case_id") or (item.event.resource.id if item.event.resource.kind == "CASE" else None)
        if case is not None and str(case) not in available_cases:
            plan.missing_inputs.append(item.name + ":case:" + str(case))
    plan.estimated_calls_upper = len(plan.items) * (config.settings.run_max_model_calls +
                                                  (config.settings.web_max_pages if web == "on" else 0))
    plan.notes.append("Upper estimate: every input uses the run call cap; each text request <=272000 bound tokens. Actual calls may be lower; per-request reservations enforce the session cap.")
    plan.notes.append("WEB_ENABLED_CAPPED: hosted search and HTTP attempts share the session ledger; missing discovery is incomplete."
                      if web == "on" else "WEB_DISABLED: pass --web on explicitly to include bounded discovery; no web coverage is claimed here.")
    try:
        prices = PriceBook.model_validate_json((ROOT / "backend/app/data/model_prices.json").read_text(encoding="utf-8"))
        models = {config.settings.model_extract, config.settings.model_agent, config.settings.model_cheap or config.settings.model_extract}
        per_call = max(prices.cost(model, TokenUsage(input_tokens=272_000, output_tokens=config.settings.llm_max_output_tokens)) for model in models)
        plan.estimated_usd_upper = per_call * plan.estimated_calls_upper
        if web == "on":
            plan.estimated_usd_upper += len(plan.items) * config.settings.web_max_searches * prices.tools.web_search_per_call
    except (SmokeFailure, OSError, ValueError):
        plan.blockers.append("MODEL_PRICE_NOT_REVIEWED")
    identity_data = {"items": [item.model_dump(mode="json", exclude={"product_dir"}) for item in plan.items], "inputs": plan.input_hashes}
    if web == "on":
        identity_data["web"] = {"mode": web, "provider": config.settings.web_provider,
                                "searches": config.settings.web_max_searches, "pages": config.settings.web_max_pages}
    plan.fingerprint = hashlib.sha256(json.dumps(identity_data, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return plan


def _story_seed(plan: StoryPlan) -> None:
    seed.reset()
    for item in plan.items:
        if item.product_dir is not None:
            seed.load_product_dir(item.product_dir)


def _story_item(item: StoryItem, mode: str) -> StoryReceipt:
    admitted = admit(item.event, role=Role.OPERATOR, actor_id="record-pass-operator")
    receipt = StoryReceipt(name=item.name, mode=mode.upper(), admission=admitted.outcome.value,
                           admission_reason=admitted.reason, status=admitted.outcome.value)
    if admitted.outcome.value == "REJECTED" and item.event.type in config.PRODUCER_EVENT_TYPES.get(item.event.producer, frozenset()):
        receipt.status = "ADMISSION_REJECTED"
    if not admitted.job_id:
        return receipt
    worker.execute_job(admitted.job_id)
    with db.transaction() as connection:
        run = connection.execute("SELECT r.* FROM runs r JOIN jobs j ON j.run_id=r.id WHERE j.id=?", (admitted.job_id,)).fetchone()
        if run is None:
            receipt.status = "RUN_MISSING"
            return receipt
        receipt.run_status = run["status"]
        # Recording completion is distinct from a published result awaiting a
        # reviewer/document. Preserve the actual lifecycle state alongside it.
        receipt.status = "COMPLETED" if run["status"] in {"COMPLETED", "WAITING_REVIEW", "WAITING_EVIDENCE"} else run["status"]
        usage = json.loads(run["usage_json"] or "{}")
        receipt.model_calls = int(usage.get("model_calls", {}).get("used", 0))
        reasons = [str(run["stop_reason"])] if run["stop_reason"] else []
        for step in connection.execute("SELECT error,detail FROM trace_steps WHERE run_id=?", (run["id"],)):
            detail = json.loads(step["detail"] or "{}")
            if step["error"] and not detail.get("retry"):
                reasons.append(str(step["error"]))
            stop = detail.get("stop_reason")
            # Scope success/normal gap terminals are not recording failures.
            if stop and ("REPLAY_MISS" in str(stop) or "ERROR" in str(stop) or "CAP" in str(stop) or "LIMIT" in str(stop)):
                reasons.append(str(stop))
        receipt.stop_reasons = sorted(set(reasons))
        if config.settings.web_search == "on" and item.event.type == "BOOTSTRAP":
            product = connection.execute("SELECT p.web_json FROM products p JOIN cases c ON c.product_id=p.id WHERE c.id=?",
                                         (run["case_id"],)).fetchone()
            enabled = bool(product and json.loads(product[0] or "{}").get("enabled"))
            terminal = connection.execute("SELECT results_json FROM web_searches WHERE run_id=? AND query=''", (run["id"],)).fetchall()
            outcomes = [json.loads(row[0]) for row in terminal if json.loads(row[0]).get("kind") == "outcome"]
            if enabled and not any(outcome.get("searches") for outcome in outcomes):
                receipt.stop_reasons.append("WEB_NOT_EXECUTED")
            for outcome in outcomes:
                if outcome.get("stop_reason"):
                    receipt.stop_reasons.append(str(outcome["stop_reason"]))
            receipt.stop_reasons = sorted(set(receipt.stop_reasons))
        if receipt.stop_reasons and receipt.status == "COMPLETED":
            receipt.status = "PARTIAL"
    return receipt


def _story_fields() -> list[str]:
    with db.transaction() as connection:
        return [json.dumps(dict(row), sort_keys=True, ensure_ascii=False) for row in connection.execute(
            "SELECT case_id,field_key,verdict,review_state,freshness,public_text,citations_json,depends_on_json "
            "FROM field_results WHERE superseded_by IS NULL ORDER BY case_id,field_key")]


def story_pass(plan: StoryPlan, output_dir: Path, *, mode: Literal["record", "replay", "fallback"] = "record",
               execute: bool = False, replay_dir: Path | None = None) -> StoryReport:
    """Record only with explicit execution; replay/fallback never contact a provider."""
    validate_caps(plan.max_calls, plan.max_usd)
    report = StoryReport(plan=plan, not_recorded=[item.name for item in plan.items])
    existing_replay_dir = replay_dir or config.settings.replay_dir
    if not execute:
        return report
    if _source_hashes(plan.fixtures_dir) != plan.input_hashes:
        raise CheckpointError("STORY_INPUT_IDENTITY_CHANGED")
    if mode == "record" and (plan.missing_inputs or plan.blockers):
        raise CheckpointError("STORY_PREFLIGHT_BLOCKED")
    if mode == "record" and (config.settings.replay_freeze or not config.settings.openai_api_key):
        raise CheckpointError("RECORD_REQUIRES_UNFROZEN_BACKEND_KEY")
    if mode == "record" and output_dir.exists():
        raise CheckpointError("OUTPUT_EXISTS_USE_NEW_DIRECTORY")
    saved = output_dir / "story-plan.json"
    if mode == "replay" and saved.is_file():
        prior = StoryPlan.model_validate_json(saved.read_text(encoding="utf-8"))
        if prior.fingerprint != plan.fingerprint:
            raise CheckpointError("STORY_INPUT_IDENTITY_CHANGED")
    ledger: PassLedger | None = None
    report.dry_run = False
    with TemporaryDirectory(prefix="p2-story-") as temporary:
        folder = Path(temporary)
        with pass_settings(folder, "base"):
            config.settings = replace(config.settings, fixtures_dir=plan.fixtures_dir)
            if mode == "replay" and saved.is_file():
                copy_database(output_dir / "base.db", folder / "base.db")
            else:
                _story_seed(plan)
        if mode == "record":
            output_dir.mkdir(parents=True, exist_ok=False)
            saved.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
            copy_database(folder / "base.db", output_dir / "base.db")
            prices = PriceBook.model_validate_json((ROOT / "backend/app/data/model_prices.json").read_text(encoding="utf-8"))
            ledger = PassLedger(output_dir / "ledger.jsonl", prices, max_calls=plan.max_calls, max_usd=plan.max_usd)
        copy_database(folder / "base.db", folder / (mode + ".db"))
        stop_recording = False

        def reserve(request: Mapping[str, object]) -> None:
            nonlocal stop_recording
            if ledger is None:
                raise CheckpointError("OFFLINE_PROVIDER_CALL_BLOCKED")
            if stop_recording:
                raise BudgetExceeded("RECORD_PASS_STOPPED")
            try:
                ledger.reserve(request)
            except (BudgetExceeded, SmokeFailure) as error:
                stop_recording = True
                raise BudgetExceeded(str(error)) from None

        with pass_settings(folder, mode, web=plan.web), network_guard(reserve):
            config.settings = replace(config.settings, fixtures_dir=plan.fixtures_dir,
                                      replay_dir=(output_dir / "replay") if mode == "record" or saved.is_file() else existing_replay_dir)
            for item in plan.items:
                active_mode = "fallback" if mode == "record" and stop_recording else mode
                config.settings = replace(config.settings, llm_mode=active_mode)
                receipt = _story_item(item, active_mode)
                report.receipts.append(receipt)
                if active_mode == "fallback":
                    report.fallback.append(item.name)
                elif receipt.status in {"COMPLETED", "NOOP", "DUPLICATE", "REJECTED"} and not receipt.stop_reasons:
                    report.not_recorded.remove(item.name)
                if mode == "record" and receipt.status not in {"COMPLETED", "NOOP", "DUPLICATE", "REJECTED"}:
                    stop_recording = True
                if ledger is not None:
                    report.network_calls, report.reserved_usd = ledger.state.calls, ledger.state.committed_usd
                    # Incremental receipt survives an interrupted later event.
                    (output_dir / "story-report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
            fields = _story_fields()
        report.complete = not plan.missing_inputs and not report.not_recorded and all(r.status in {"COMPLETED", "NOOP", "DUPLICATE", "REJECTED"} for r in report.receipts)
        if mode == "record":
            (output_dir / "story-results.json").write_text(json.dumps(fields, ensure_ascii=False, indent=2), encoding="utf-8")
            (output_dir / "story-report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
        elif mode == "replay" and (output_dir / "story-results.json").is_file():
            expected = json.loads((output_dir / "story-results.json").read_text(encoding="utf-8"))
            report.replay_equal = report.complete and fields == expected
            report.complete = report.complete and report.replay_equal
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path, nargs="?", help="One LISTING snapshot JSON; no gold labels")
    parser.add_argument("--events", type=Path, nargs="+", help="Phase-2 bootstrap events; dry by default")
    parser.add_argument("--replay-only", action="store_true", help="Recheck a saved pass using its identical base database")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "backend/.venv/p2-record-checkpoint")
    parser.add_argument("--execute", action="store_true", help="Human terminal only: allow capped record, then replay and fallback")
    parser.add_argument("--story", action="store_true", help="Storyboard events, remaining events, then blind set 1 (default with no input)")
    parser.add_argument("--storyboard", type=Path, default=ROOT / "scripts/demo/storyboard.md")
    parser.add_argument("--dry-run", action="store_true", help="Plan only; never execute")
    parser.add_argument("--mode", choices=("record", "replay", "fallback"), default=None, help="Story mode; replay/fallback explicitly execute offline unless --dry-run")
    parser.add_argument("--max-calls", type=int, default=30, help="Finite story network request cap (default 30)")
    parser.add_argument("--max-usd", type=float, default=2.0, help="Finite story USD reservation cap (default 2)")
    parser.add_argument("--replay-dir", type=Path, help="Existing story recordings when no saved base/plan is available")
    parser.add_argument("--web", choices=("off", "on"), default="off", help="Story web discovery; defaults off, shared session cap when on")
    args = parser.parse_args()
    try:
        validate_caps(args.max_calls, args.max_usd)
        if args.dry_run and (args.execute or args.replay_only):
            raise CheckpointError("INCOMPATIBLE_OPTIONS")
        if args.story or (not args.events and not args.snapshot):
            if args.events or args.snapshot or (args.execute and args.replay_only):
                raise CheckpointError("INCOMPATIBLE_OPTIONS")
            plan = story_plan(storyboard=args.storyboard, max_calls=args.max_calls, max_usd=args.max_usd, web=args.web)
            estimate = f"${plan.estimated_usd_upper:.6f}" if plan.estimated_usd_upper is not None else "UNKNOWN"
            print(f"Story plan: <= {plan.estimated_calls_upper} calls; USD upper={estimate}; caps={plan.max_calls} calls / ${plan.max_usd:.6f}", flush=True)
            mode = "replay" if args.replay_only else (args.mode or "record")
            report = story_pass(plan, args.output_dir.resolve(), mode=mode,
                execute=not args.dry_run and (args.execute or mode in {"replay", "fallback"}), replay_dir=args.replay_dir or config.settings.replay_dir)
        elif args.mode or args.replay_dir or args.web != "off" or args.max_calls != 30 or args.max_usd != 2.0:
            raise CheckpointError("STORY_OPTIONS_REQUIRE_STORY")
        elif args.events:
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
    if isinstance(report, StoryReport) and (report.plan.missing_inputs or report.plan.blockers or (not report.dry_run and not report.complete)):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
