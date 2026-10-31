"""P1 gap controller interface; implementation due at S3."""
from dataclasses import dataclass
from app.context import RunContext
from app.models import FieldDecision
from app.pipeline.policy import SourceObs


@dataclass
class GapOutcome:
    new_sv_ids: list[str]
    stops: list[str]


def close_gaps(ctx: RunContext, decisions: list[FieldDecision], observations: list[SourceObs]) -> GapOutcome:
    return GapOutcome([], [])
