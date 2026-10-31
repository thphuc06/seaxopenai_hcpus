"""P2 web discovery interface; implementation due at S4."""
from dataclasses import dataclass
from pydantic import JsonValue
from app.context import RunContext


@dataclass
class WebOutcome:
    new_sv_ids: list[str]
    searches: list[dict[str, JsonValue]]
    stop_reason: str | None


def discover(ctx: RunContext) -> WebOutcome:
    return WebOutcome([], [], None)
