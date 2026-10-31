"""Budgeted Responses gateway with immutable, schema-validated recordings."""
from __future__ import annotations

import asyncio
import base64
from collections.abc import Callable, Iterator, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from threading import Event
from time import perf_counter
from typing import Generic, Literal, TypeVar

from openai import APIError, APIStatusError, OpenAI
from openai.types.responses import Response
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from app import config
from app.budget import BudgetExceeded
from app.context import RunContext
from app.llm.messages import ImagePart, InputMessage, TextPart, build_input

SchemaT = TypeVar("SchemaT", bound=BaseModel)
ErrorCode = Literal["INCOMPLETE", "REFUSAL", "REPLAY_MISS", "API_ERROR"]
_cancelled: ContextVar[Event | None] = ContextVar("llm_cancelled", default=None)
_network_guard: ContextVar[Callable[[Mapping[str, object]], None] | None] = ContextVar("llm_network_guard", default=None)


@contextmanager
def network_guard(reserve: Callable[[Mapping[str, object]], None]) -> Iterator[None]:
    """Additional server-side spending cap; never replaces the per-run Budget."""
    token = _network_guard.set(reserve)
    try:
        yield
    finally:
        _network_guard.reset(token)


class LLMError(Exception):
    def __init__(self, code: ErrorCode, reason: str | None = None) -> None:
        self.code = code
        self.reason = reason
        super().__init__(code if reason is None else f"{code}:{reason}")


def reserve_network(request: Mapping[str, object]) -> None:
    """Apply the bound session ledger before a model or HTTP provider attempt."""
    guard = _network_guard.get()
    if guard is not None:
        guard(request)


@dataclass(frozen=True)
class LLMResult(Generic[SchemaT]):
    parsed: SchemaT
    usage: dict[str, JsonValue]
    replayed: bool
    model: str


class TokenUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    reasoning_tokens: int = Field(default=0, ge=0)


class Recording(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    key: str
    step: str
    model: str
    prompt_version: str
    output_schema: dict[str, JsonValue] = Field(alias="schema")
    created_at: str
    output: JsonValue
    usage: TokenUsage
    status: Literal["completed"]


def _call_api(**request: object) -> Response:
    """The sole replaceable external-client seam; SDK retries are disabled."""
    timeout = request.pop("timeout")
    with OpenAI(api_key=config.settings.openai_api_key, timeout=timeout, max_retries=0) as provider:
        raw = provider.responses.with_raw_response.parse(**request)
        envelope = Response.model_validate_json(raw.content)
        # Installed SDK 3.42 parses output text even when incomplete. Inspect the
        # envelope first so truncated JSON retains its status and measured usage.
        if envelope.status != "completed" or any(
            item.type == "message" and any(part.type == "refusal" for part in item.content)
            for item in envelope.output
        ):
            return envelope
        try:
            return raw.parse()
        except ValidationError:
            # Our boundary reports INVALID_OUTPUT after accounting envelope usage.
            return envelope


def _active(ctx: RunContext) -> None:
    cancelled = _cancelled.get()
    if cancelled is not None and cancelled.is_set():
        raise asyncio.CancelledError()
    ctx.budget.check_active()


def _request(ctx: RunContext, **request: object) -> Response:
    """Bound caller latency even if a provider ignores its transport timeout.

    The worker performs only the provider request. Usage, traces and recordings
    remain on the calling thread, so a late result cannot publish side effects.
    """
    reserve_network(request)
    _active(ctx)
    wait_deadline = perf_counter() + ctx.budget.remaining_s()
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="llm-request")
    future = pool.submit(_call_api, **request)
    try:
        return future.result(timeout=max(0.0, wait_deadline - perf_counter()))
    except TimeoutError:
        if future.done() and future.exception() is not None:
            raise
        ctx.budget.expire()
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def _identity(*, step: str, model: str, prompt_version: str, instructions: str,
              input_parts: Sequence[TextPart | ImagePart], schema: type[BaseModel],
              effort: str, max_output_tokens: int) -> tuple[str, list[InputMessage]]:
    messages = build_input(instructions, input_parts)
    # Hash the exact image bytes built for the request, avoiding a second path read.
    identity_messages = json.loads(json.dumps(messages))
    for message in identity_messages:
        for part in message["content"]:
            if part["type"] == "input_image":
                png = base64.b64decode(part.pop("image_url").split(",", 1)[1], validate=True)
                part["image_sha256"] = hashlib.sha256(png).hexdigest()
    identity = {"model": model, "step": step, "prompt_version": prompt_version,
                "input": identity_messages, "schema": schema.model_json_schema(),
                "reasoning": {"effort": effort}, "max_output_tokens": max_output_tokens, "tools": []}
    encoded = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest(), messages


def _record_path(step: str, key: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_:-]+", step):
        raise ValueError("Invalid replay step")
    return config.settings.replay_dir / step.replace(":", "_") / f"{key}.json"


def _load(path: Path, *, key: str, step: str, model: str, prompt_version: str,
          schema: type[SchemaT]) -> SchemaT:
    try:
        recording = Recording.model_validate_json(path.read_text(encoding="utf-8"))
        if (recording.key, recording.step, recording.model, recording.prompt_version, recording.output_schema) != (
            key, step, model, prompt_version, schema.model_json_schema()
        ):
            raise LLMError("API_ERROR", "INVALID_RECORDING")
        return schema.model_validate(recording.output, strict=True)
    except FileNotFoundError:
        raise LLMError("REPLAY_MISS") from None
    except (ValidationError, OSError, ValueError):
        raise LLMError("API_ERROR", "INVALID_RECORDING") from None


def _append(path: Path, recording: Recording, ctx: RunContext) -> None:
    """Publish a complete file atomically; never replace a concurrent winner."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".record-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(recording.model_dump_json(by_alias=True))
            output.flush()
            os.fsync(output.fileno())
        try:
            _active(ctx)
            os.link(temporary, path)
        except FileExistsError:
            pass  # Another complete, immutable recording won the race.
    finally:
        Path(temporary).unlink(missing_ok=True)


def _usage(response: Response) -> TokenUsage:
    usage = response.usage
    if usage is None:
        return TokenUsage()
    return TokenUsage(input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
                      reasoning_tokens=usage.output_tokens_details.reasoning_tokens)


def _parsed(response: Response, schema: type[SchemaT]) -> SchemaT:
    if response.status == "incomplete":
        reason = response.incomplete_details.reason if response.incomplete_details else "unknown"
        raise LLMError("INCOMPLETE", reason)
    for item in response.output:
        if item.type == "message" and any(part.type == "refusal" for part in item.content):
            raise LLMError("REFUSAL")
    if response.status != "completed":
        raise LLMError("API_ERROR", "INVALID_STATUS")
    try:
        return schema.model_validate_json(response.output_text, strict=True)
    except ValidationError:
        raise LLMError("API_ERROR", "INVALID_OUTPUT") from None


def parse(
    *, step: str, model: str, instructions: str,
    input_parts: Sequence[TextPart | ImagePart], schema: type[SchemaT],
    ctx: RunContext, prompt_version: str, effort: str | None = None,
    max_output_tokens: int | None = None,
) -> LLMResult[SchemaT]:
    mode = ctx.mode
    if mode == "fallback":
        raise LLMError("API_ERROR", "FALLBACK_MODE")
    if mode not in {"live", "record", "replay"}:
        raise LLMError("API_ERROR", "INVALID_MODE")
    settings = config.settings
    selected_effort = effort or (settings.llm_effort_agent if step.startswith("agent:") else settings.llm_effort_extract)
    cap = settings.llm_max_output_tokens if max_output_tokens is None else max_output_tokens
    key, messages = _identity(step=step, model=model, prompt_version=prompt_version,
                              instructions=instructions, input_parts=input_parts, schema=schema,
                              effort=selected_effort, max_output_tokens=cap)
    path = _record_path(step, key)
    replay_only = mode == "replay" or settings.replay_freeze
    for attempt in range(2):
        _active(ctx)
        ctx.budget.take_model_call(step)
        started = perf_counter()
        usage = TokenUsage()
        replayed = False
        error_code: str | None = None
        retry = False
        try:
            if replay_only or (mode == "record" and path.exists()):
                parsed = _load(path, key=key, step=step, model=model, prompt_version=prompt_version, schema=schema)
                replayed = True
                _active(ctx)
                return LLMResult(parsed, usage.model_dump(), True, model)
            response = _request(ctx, model=model, input=messages, text_format=schema,
                                 reasoning={"effort": selected_effort}, max_output_tokens=cap,
                                 timeout=ctx.budget.remaining_s())
            usage = _usage(response)
            ctx.budget.record_usage(**usage.model_dump())
            _active(ctx)
            parsed = _parsed(response, schema)
            if mode == "record":
                try:
                    _append(path, Recording(key=key, step=step, model=model, prompt_version=prompt_version,
                                            schema=schema.model_json_schema(), created_at=datetime.now(timezone.utc).isoformat(),
                                            output=parsed.model_dump(mode="json"), usage=usage, status="completed"), ctx)
                except OSError:
                    raise LLMError("API_ERROR", "RECORDING_WRITE_FAILED") from None
            return LLMResult(parsed, usage.model_dump(), False, response.model)
        except APIStatusError as error:
            error_code = "API_ERROR"
            retry = attempt == 0 and (error.status_code == 429 or error.status_code >= 500)
            if not retry:
                raise LLMError("API_ERROR", f"HTTP_{error.status_code}") from None
        except (APIError, ValidationError):
            error_code = "API_ERROR"
            raise LLMError("API_ERROR") from None
        except (LLMError, BudgetExceeded) as error:
            error_code = str(error)
            raise
        finally:
            cancelled = _cancelled.get()
            if cancelled is None or not cancelled.is_set():
                ctx.trace.step(step, actor="llm", latency_ms=(perf_counter() - started) * 1000,
                               tokens_in=usage.input_tokens, tokens_out=usage.output_tokens, error=error_code,
                               detail={"replayed": replayed, "model": model, "prompt_version": prompt_version,
                                       "mode": "REPLAY" if replayed else mode.upper(), "attempt": attempt + 1,
                                       "retry": retry, "reasoning_tokens": usage.reasoning_tokens,
                                       "budget": ctx.budget.usage()})
    raise LLMError("API_ERROR")


async def aparse(
    *, step: str, model: str, instructions: str,
    input_parts: Sequence[TextPart | ImagePart], schema: type[SchemaT],
    ctx: RunContext, prompt_version: str, effort: str | None = None,
    max_output_tokens: int | None = None,
) -> LLMResult[SchemaT]:
    _active(ctx)
    cancelled = Event()
    token = _cancelled.set(cancelled)
    try:
        return await asyncio.wait_for(asyncio.to_thread(
            parse, step=step, model=model, instructions=instructions, input_parts=input_parts,
            schema=schema, ctx=ctx, prompt_version=prompt_version, effort=effort,
            max_output_tokens=max_output_tokens), timeout=ctx.budget.remaining_s())
    except TimeoutError:
        cancelled.set()
        ctx.budget.check_active()
        raise BudgetExceeded("RUN_DEADLINE") from None
    except asyncio.CancelledError:
        cancelled.set()
        raise
    finally:
        _cancelled.reset(token)
