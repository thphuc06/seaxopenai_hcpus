"""Offline B1 orchestration. Kept outside the application publication lifecycle."""
from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3
from typing import Literal

from pydantic import BaseModel, Field, JsonValue, ValidationError

from app import config
from app.budget import Budget, BudgetExceeded
from app.context import RunContext
from app.llm.client import LLMError
from app.pipeline.baseline import (B1_INSTRUCTIONS, B1_MAX_OUTPUT_TOKENS, B1_VERSION,
    B1Prediction, BaselinePassage, BaselineSource, b1_input, predict_once)
from app.trace import TraceWriter


class BaselineTrace(TraceWriter):
    """TraceWriter-compatible diagnostic sink; never changes candidate database rows."""
    def __init__(self) -> None:
        self.rows: list[dict[str, JsonValue]] = []

    def step(self, step: str, actor: str = "code", input_refs: JsonValue = None,
             output_refs: JsonValue = None, detail: JsonValue = None, latency_ms: float = 0,
             tokens_in: int = 0, tokens_out: int = 0, error: str | None = None) -> None:
        self.rows.append(dict(step=step, actor=actor, input_refs=input_refs, output_refs=output_refs,
            detail=detail, latency_ms=latency_ms, tokens_in=tokens_in, tokens_out=tokens_out, error=error))


class B1Report(BaseModel):
    version: str = B1_VERSION
    mode: Literal["off", "record", "replay"] = "off"
    status: str = "NOT_RUN"
    model: str | None = None
    prediction: B1Prediction | None = None
    calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    estimated_max_usd: float | None = None
    trace: list[dict[str, JsonValue]] = Field(default_factory=list)


def sources_and_context(database: Path, case_id: str, mode: str) -> tuple[list[BaselineSource], RunContext]:
    with closing(sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute("SELECT c.tenant_id,c.revision,p.* FROM cases c JOIN products p ON p.id=c.product_id WHERE c.id=?",
                                 (case_id,)).fetchone()
        if row is None:
            raise ValueError("B1 case does not exist")
        product = {key: row[key] for key in ("id", "name", "brand", "variant", "market")}
        ctx = RunContext("baseline-diagnostic", case_id, row["tenant_id"], row["revision"],
            product, mode, Budget(max_model_calls=1, deadline_s=min(config.settings.run_deadline_s, 120)), BaselineTrace())
        sources: list[BaselineSource] = []
        for source in connection.execute("SELECT sv.id,sv.scope_json,s.kind,s.family,s.status FROM source_versions sv "
                "JOIN sources s ON s.id=sv.source_id WHERE s.case_id=? AND sv.is_current=1 ORDER BY s.id", (case_id,)):
            passages = [BaselinePassage.model_validate(dict(p)) for p in connection.execute(
                "SELECT id,locator,text FROM passages WHERE source_version_id=? ORDER BY rowid", (source["id"],))]
            sources.append(BaselineSource(id=source["id"], kind=source["kind"], family=source["family"],
                status=source["status"], scope=json.loads(source["scope_json"] or "null"), passages=passages))
    return sources, ctx


def estimated_cost(sources: list[BaselineSource], ctx: RunContext, model: str) -> float:
    prices = json.loads((Path(__file__).resolve().parents[1] / "backend/app/data/model_prices.json").read_text(encoding="utf-8"))
    rate = prices["models"].get(model)
    if rate is None:
        raise ValueError("B1 model price is unknown; record is not permitted")
    # One UTF-8 byte per token plus a framing allowance is deliberately conservative.
    input_cap = len((b1_input(sources, ctx) + B1_INSTRUCTIONS + json.dumps(
        B1Prediction.model_json_schema())).encode("utf-8")) + 2048
    return (input_cap * rate["input_per_million"] + B1_MAX_OUTPUT_TOKENS * rate["output_per_million"]) / 1_000_000


class B1Session:
    def __init__(self, mode: Literal["off", "record", "replay"] = "off", max_calls: int = 0) -> None:
        if max_calls < 0:
            raise ValueError("max_calls must be nonnegative")
        self.mode = mode
        self.remaining = max_calls
        self.spending_bound = 0.0

    def evaluate(self, database: Path, case_id: str) -> B1Report:
        report = B1Report(mode=self.mode)
        if self.mode == "off":
            return report
        if not self.remaining:
            report.status = "CALL_CAP"
            return report
        model = config.settings.model_extract
        if not model:
            report.status = "MODEL_NOT_CONFIGURED"
            return report
        sources, ctx = sources_and_context(database, case_id, self.mode)
        report.model = model
        if self.mode == "record":
            report.estimated_max_usd = estimated_cost(sources, ctx, model)
            if self.spending_bound + report.estimated_max_usd > 3:
                report.status = "COST_CAP_REQUIRES_APPROVAL"
                return report
            print(f"B1 record upper estimate ${report.estimated_max_usd:.4f}; session cap $3; remaining calls {self.remaining}", flush=True)
            self.spending_bound += report.estimated_max_usd
        try:
            result = predict_once(sources, ctx, model)
            report.prediction = result.parsed
            report.status = "REPLAY" if result.replayed else "RECORDED"
        except (LLMError, BudgetExceeded) as error:
            report.status = error.code if isinstance(error, LLMError) else error.reason
        except ValidationError:
            report.status = "INVALID_SCHEMA"
        finally:
            report.calls = ctx.budget.model_calls
            self.remaining -= report.calls
            usage = ctx.budget.usage()["tokens"]
            report.tokens_in = int(usage["input_tokens"])
            report.tokens_out = int(usage["output_tokens"])
            assert isinstance(ctx.trace, BaselineTrace)
            report.trace = ctx.trace.rows
        return report
