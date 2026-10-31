"""P2 extraction/audit interface; delegates decisions to P1 policy at S2."""
from app.context import RunContext
from app.models import FieldDecision
from app.pipeline.policy import SourceObs


def audit(ctx: RunContext, listing_obs: list[SourceObs], observations: list[SourceObs]) -> list[FieldDecision]:
    return []
