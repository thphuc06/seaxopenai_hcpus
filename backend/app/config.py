"""Shared server settings. Relative paths are anchored to backend/, not cwd."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Literal, cast

from dotenv import dotenv_values
from pydantic import JsonValue

BACKEND_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = BACKEND_DIR / ".env"
LLMMode = Literal["fallback", "replay", "record", "live"]


@dataclass
class Settings:
    openai_api_key: str = field(default="", repr=False)
    llm_mode: LLMMode = "fallback"
    model_extract: str = ""
    model_agent: str = ""
    model_cheap: str = ""
    embed_model: str = "text-embedding-3-small"
    llm_effort_extract: str = "low"
    llm_effort_agent: str = "medium"
    llm_max_output_tokens: int = 16000
    replay_dir: Path = BACKEND_DIR.parent / "fixtures" / "replay"
    llm_vision: bool = True
    run_max_model_calls: int = 24
    run_deadline_s: float = 120.0
    agent_max_model_calls: int = 10
    agent_max_tool_calls: int = 16
    agent_manager_turns: int = 3
    agent_retrieval_hops: int = 2
    agent_deadline_s: float = 75.0
    agent_single_call_max: int = 8
    web_search: Literal["on", "off"] = "off"
    web_provider: Literal["openai", "tavily"] = "openai"
    web_max_searches: int = 3
    web_max_pages: int = 4
    ocr_enabled: bool = True
    agents_tracing: bool = True
    replay_freeze: bool = False
    worker_inline: bool = False
    demo_run_delay_s: float = 0.0
    db_path: Path = BACKEND_DIR / "passport.db"
    fixtures_dir: Path = BACKEND_DIR.parent / "fixtures"
    contest_phase: int = 0
    model_prices: dict[str, JsonValue] = field(default_factory=dict)

    @property
    def price_status(self) -> str:
        return "available" if self.model_prices else "price unknown"


def _load() -> Settings:
    values = {**dotenv_values(ENV_FILE, encoding="utf-8"), **os.environ}
    result = Settings()
    phase_file = BACKEND_DIR / "tests" / "PHASE"
    if phase_file.exists():
        result.contest_phase = int(phase_file.read_text(encoding="utf-8").strip())
    for item in fields(result):
        if item.name == "model_prices":
            continue
        raw = values.get(item.name.upper())
        if raw is None or (item.name == "contest_phase" and raw == ""):
            continue
        default = getattr(result, item.name)
        if isinstance(default, bool):
            if raw.lower() not in {"0", "1", "true", "false", "on", "off"}:
                raise ValueError(f"Invalid boolean setting: {item.name.upper()}")
            parsed: str | int | float | bool | Path = raw.lower() in {"1", "true", "on"}
        elif isinstance(default, int):
            parsed = int(raw)
            if parsed < 0:
                raise ValueError(f"Negative setting: {item.name.upper()}")
        elif isinstance(default, float):
            parsed = float(raw)
            if not 0 <= parsed < float("inf"):
                raise ValueError(f"Invalid finite duration: {item.name.upper()}")
        elif isinstance(default, Path):
            path = Path(raw)
            parsed = path if path.is_absolute() else (BACKEND_DIR / path).resolve()
        else:
            parsed = raw
        setattr(result, item.name, parsed)
    for name, allowed in (
        ("llm_mode", {"fallback", "replay", "record", "live"}),
        ("web_search", {"on", "off"}),
        ("web_provider", {"openai", "tavily"}),
    ):
        if getattr(result, name) not in allowed:
            raise ValueError(f"Invalid setting: {name.upper()}")
    price_file = BACKEND_DIR / "app" / "data" / "model_prices.json"
    if price_file.exists():
        prices = json.loads(price_file.read_text(encoding="utf-8"))
        if not isinstance(prices, dict):
            raise ValueError("model_prices.json must contain an object")
        result.model_prices = cast(dict[str, JsonValue], prices)
    return result


settings = _load()


def reload_settings() -> Settings:
    """Refresh in place so consumers retaining settings see the new values."""
    updated = _load()
    for item in fields(updated):
        setattr(settings, item.name, getattr(updated, item.name))
    return settings
