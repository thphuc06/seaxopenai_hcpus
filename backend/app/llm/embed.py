"""Budgeted embedding provider seam; immutable recordings, no implicit calls."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from time import perf_counter
from typing import Literal

from openai import APIError, OpenAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app import config
from app.budget import BudgetExceeded
from app.context import RunContext
from app.llm import client

VERSION = "embed-v1"


class Vector(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    values: list[float] = Field(min_length=1)


class EmbeddingItem(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    embedding: list[float] = Field(min_length=1)
    index: int = Field(ge=0)
    object: Literal["embedding"]


class EmbeddingUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    prompt_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)


class ProviderResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    data: list[EmbeddingItem]
    model: str
    object: Literal["list"]
    usage: EmbeddingUsage


@dataclass(frozen=True)
class EmbeddingResult:
    vector: list[float]
    model: str
    replayed: bool


def _call_api(*, model: str, input: str, encoding_format: Literal["float"], timeout: float) -> ProviderResponse:
    """Only embedding network seam; tests replace this provider, not ranking."""
    with OpenAI(api_key=config.settings.openai_api_key, timeout=timeout, max_retries=0) as provider:
        response = provider.embeddings.create(model=model, input=input, encoding_format=encoding_format)
        return ProviderResponse.model_validate(response.model_dump(), strict=True)


def validate_vector(values: object) -> list[float]:
    vector = Vector.model_validate({"values": values}, strict=True).values
    norm = math.hypot(*vector)
    if not math.isfinite(norm) or norm == 0:
        raise ValueError("INVALID_VECTOR_NORM")
    return vector


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _wire(text: str) -> str:
    return "<SOURCE_DATA>\n" + text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") + "\n</SOURCE_DATA>"


def _identity(text: str) -> dict[str, object]:
    return {"model": config.settings.embed_model, "prompt_version": VERSION, "input": _wire(text),
            "encoding_format": "float", "schema": Vector.model_json_schema(), "tools": []}


def cache_identity(text: str) -> str:
    """Invalidate persisted vectors when model, schema or wire format changes."""
    return content_hash(json.dumps(_identity(text), sort_keys=True, ensure_ascii=False, separators=(",", ":")))


def embed(text: str, *, ctx: RunContext, step: Literal["embed:ingest", "embed:query"]) -> EmbeddingResult:
    """One input per budgeted call, including replay hits. Cache is caller-owned."""
    if ctx.mode == "fallback":
        raise client.LLMError("API_ERROR", "FALLBACK_MODE")
    if ctx.mode not in {"record", "replay", "live"} or not text.strip():
        raise client.LLMError("API_ERROR", "INVALID_INPUT")
    model = config.settings.embed_model
    wire = _wire(text)
    identity = _identity(text) | {"step": step}
    key = content_hash(json.dumps(identity, sort_keys=True, ensure_ascii=False, separators=(",", ":")))
    path = client._record_path(step, key)
    replayed = ctx.mode == "replay" or config.settings.replay_freeze or (ctx.mode == "record" and path.exists())
    usage = client.TokenUsage()
    error_code: str | None = None
    started = perf_counter()
    try:
        client._active(ctx)
        ctx.budget.take_model_call(step)
        if replayed:
            parsed = client._load(path, key=key, step=step, model=model, prompt_version=VERSION, schema=Vector)
            vector = validate_vector(parsed.values)
        else:
            request = {"model": model, "input": wire, "encoding_format": "float", "timeout": ctx.budget.remaining_s()}
            guard = client._network_guard.get()
            if guard is not None:
                # The shared pass ledger prices a generic request plus its
                # output cap. Embeddings have no generated output tokens.
                guard(request | {"max_output_tokens": 0})
            client._active(ctx)
            pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="embed-request")
            future = pool.submit(_call_api, model=model, input=wire, encoding_format="float", timeout=ctx.budget.remaining_s())
            try:
                response = future.result(timeout=ctx.budget.remaining_s())
            except TimeoutError:
                ctx.budget.expire()
            finally:
                pool.shutdown(wait=False, cancel_futures=True)
            usage = client.TokenUsage(input_tokens=response.usage.prompt_tokens)
            ctx.budget.record_usage(input_tokens=usage.input_tokens, output_tokens=0, reasoning_tokens=0)
            client._active(ctx)
            if response.model != model or len(response.data) != 1 or response.data[0].index != 0:
                raise client.LLMError("API_ERROR", "INVALID_EMBEDDING_RESPONSE")
            vector = validate_vector(response.data[0].embedding)
            if ctx.mode == "record":
                client._append(path, client.Recording(
                    key=key, step=step, model=model, prompt_version=VERSION,
                    schema=Vector.model_json_schema(), created_at=datetime.now(timezone.utc).isoformat(),
                    output=Vector(values=vector).model_dump(mode="json"), usage=usage, status="completed"), ctx)
        client._active(ctx)
        return EmbeddingResult(vector, model, replayed)
    except OSError as error:
        error_code = f"API_ERROR:EMBEDDING_STORAGE_{error.errno}"
        raise client.LLMError("API_ERROR", f"EMBEDDING_STORAGE_{error.errno}") from None
    except (APIError, ValidationError, ValueError):
        error_code = "API_ERROR:INVALID_EMBEDDING_RESPONSE"
        raise client.LLMError("API_ERROR", "INVALID_EMBEDDING_RESPONSE") from None
    except (client.LLMError, BudgetExceeded) as error:
        error_code = str(error)
        raise
    finally:
        ctx.trace.step(step, actor="llm", tokens_in=usage.input_tokens,
                       latency_ms=(perf_counter() - started) * 1000, error=error_code,
                       detail={"mode": "REPLAY" if replayed else ctx.mode.upper(), "replayed": bool(replayed),
                               "model": model, "prompt_version": VERSION, "budget": ctx.budget.usage()})
