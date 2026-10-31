"""P2 scope interfaces; implementation due at S3."""
from dataclasses import dataclass
from typing import Literal
from app.context import RunContext
from app.models import ScopeMatch
from app.pipeline.policy import SourceObs


@dataclass
class PassageScope:
    passage_id: str
    sv_id: str
    scope_match: ScopeMatch
    decided_by: Literal["CODE", "AGENT_VERIFIED", "AGENT", "FIXED_WORKFLOW", "REPLAY"]
    anchor_passage_id: str | None
    reason: str


@dataclass
class ScopeOutcome:
    decisions: list[PassageScope]
    changed: bool
    stop_reason: str | None
    effect_note: str


def resolve_all(ctx: RunContext, observations: list[SourceObs], fields: list[str]) -> ScopeOutcome:
    return ScopeOutcome([], False, None, "Scope resolution pending S3")
