"""Phase-0 typed client contract. Execution modes are implemented in Phase 1."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, JsonValue

from app.context import RunContext
from app.llm.messages import ImagePart, TextPart


SchemaT = TypeVar("SchemaT", bound=BaseModel)
ErrorCode = Literal["INCOMPLETE", "REFUSAL", "REPLAY_MISS", "API_ERROR"]


class LLMError(Exception):
    def __init__(self, code: ErrorCode) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class LLMResult(Generic[SchemaT]):
    parsed: SchemaT
    usage: dict[str, JsonValue]
    replayed: bool
    model: str


def _call_api(**request: object) -> BaseModel:
    """The replaceable network seam; disabled until the Phase-1 implementation."""
    raise LLMError("API_ERROR")


def parse(
    *, step: str, model: str, instructions: str,
    input_parts: Sequence[TextPart | ImagePart], schema: type[SchemaT],
    ctx: RunContext, prompt_version: str, effort: str | None = None,
    max_output_tokens: int | None = None,
) -> LLMResult[SchemaT]:
    """Fail explicitly in S0 rather than creating output from an unfinished mode."""
    raise LLMError("REPLAY_MISS" if ctx.mode == "replay" else "API_ERROR")


async def aparse(
    *, step: str, model: str, instructions: str,
    input_parts: Sequence[TextPart | ImagePart], schema: type[SchemaT],
    ctx: RunContext, prompt_version: str, effort: str | None = None,
    max_output_tokens: int | None = None,
) -> LLMResult[SchemaT]:
    """Async contract with the same explicit S0 failure semantics."""
    return parse(step=step, model=model, instructions=instructions, input_parts=input_parts,
                 schema=schema, ctx=ctx, prompt_version=prompt_version,
                 effort=effort, max_output_tokens=max_output_tokens)
