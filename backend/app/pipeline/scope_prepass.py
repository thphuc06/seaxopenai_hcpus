"""P2 code pre-pass stub; implementation due at S3."""
from app.agent.scope_resolution import ScopeOutcome
from app.context import RunContext
from app.pipeline.policy import SourceObs


def resolve_all(ctx: RunContext, observations: list[SourceObs], fields: list[str]) -> ScopeOutcome:
    return ScopeOutcome([], False, None, "Scope pre-pass pending S3")
