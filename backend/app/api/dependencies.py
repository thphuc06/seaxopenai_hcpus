"""Demo identity comes from request headers, never event/model arguments."""
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException

from app.models import Role


@dataclass(frozen=True)
class RequestActor:
    role: Role
    actor_id: str


def request_actor(
    x_demo_role: Annotated[str | None, Header()] = None,
    x_demo_actor: Annotated[str | None, Header()] = None,
) -> RequestActor:
    if x_demo_role not in {role.value for role in Role} or not x_demo_actor or not x_demo_actor.strip():
        raise HTTPException(status_code=403, detail="Role and actor headers are required")
    return RequestActor(role=Role(x_demo_role), actor_id=x_demo_actor.strip())


Actor = Annotated[RequestActor, Depends(request_actor)]


def operator_actor(actor: Actor) -> RequestActor:
    if actor.role != Role.OPERATOR:
        raise HTTPException(status_code=403, detail="Operator role required")
    return actor


def event_actor(actor: Actor) -> RequestActor:
    if actor.role not in {Role.OPERATOR, Role.SYSTEM}:
        raise HTTPException(status_code=403, detail="Event submission role required")
    return actor


def run_actor(actor: Actor) -> RequestActor:
    if actor.role not in {Role.OPERATOR, Role.REVIEWER}:
        raise HTTPException(status_code=403, detail="Run access role required")
    return actor


OperatorActor = Annotated[RequestActor, Depends(operator_actor)]
EventActor = Annotated[RequestActor, Depends(event_actor)]
RunActor = Annotated[RequestActor, Depends(run_actor)]


def reviewer_actor(actor: Actor) -> RequestActor:
    if actor.role != Role.REVIEWER:
        raise HTTPException(status_code=403, detail="Reviewer role required")
    return actor


def evidence_actor(actor: Actor) -> RequestActor:
    if actor.role not in {Role.SELLER, Role.REVIEWER}:
        raise HTTPException(status_code=403, detail="Evidence submission role required")
    return actor


ReviewerActor = Annotated[RequestActor, Depends(reviewer_actor)]
EvidenceActor = Annotated[RequestActor, Depends(evidence_actor)]
