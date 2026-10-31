"""P1 owns RunContext; real trace/storage arrives at S0."""
from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING
from pydantic import JsonValue
from app.budget import Budget

if TYPE_CHECKING:
    from app.trace import TraceWriter


@dataclass
class RunContext:
    run_id: str
    case_id: str
    tenant_id: str
    case_revision: int
    product: dict[str, JsonValue]
    mode: str
    budget: Budget
    trace: TraceWriter
