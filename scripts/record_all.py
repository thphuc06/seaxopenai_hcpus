"""Phase-1 single-LISTING checkpoint; dry by default, --execute in human terminal.

This does not run/publish a bootstrap or generate expected labels. Each output
directory permits one paid attempt (at most two requests including retry).
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from typing import Iterator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from pydantic import BaseModel, ConfigDict, Field

from app import config, db, store
from app.budget import Budget, BudgetExceeded
from app.context import RunContext
from app.llm.client import LLMError
from app.llm.messages import build_input
from app.models import ClaimExtraction
from app.pipeline.extract import INSTRUCTIONS, PROMPT_VERSION, Extraction, extract_source_version, extraction_input
from app.pipeline.fallback_extract import FALLBACK_VERSION, Passage
from app.trace import TraceWriter
from scripts.smoke import PriceBook, SmokeFailure, TokenUsage, request_bound


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
    budget = Budget(max_model_calls=2 if mode == "record" else 1 if mode == "replay" else 0, max_tool_calls=0)
    ctx = RunContext(mode, "checkpoint", "operator", 0, {"id": product_id}, mode, budget, TraceWriter(mode))
    result = extract_source_version(sv_id, ctx)
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
                PROMPT_VERSION, INSTRUCTIONS, ClaimExtraction.model_json_schema(), FALLBACK_VERSION]
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path, help="One LISTING snapshot JSON; no gold labels")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "backend/.venv/p2-record-checkpoint")
    parser.add_argument("--execute", action="store_true", help="Human terminal only: allow capped record, then replay and fallback")
    args = parser.parse_args()
    try:
        report = checkpoint(args.snapshot.resolve(), args.output_dir.resolve(), execute=args.execute)
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
