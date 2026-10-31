"""Shared run and agent accounting without network, wall-clock waits or patching."""

from dataclasses import dataclass

import pytest

from app.budget import AgentBudget, Budget, BudgetExceeded


@dataclass
class Clock:
    now: float = 100.0

    def __call__(self) -> float:
        return self.now


def test_agent_budget_reuses_parent_counters() -> None:
    parent = Budget(max_model_calls=5)
    parent.take_model_call("extract")
    child = parent.agent()
    child.take_model_call("scope")
    child.take_tool("read_passage")
    assert parent.model_calls == 2
    assert parent.tool_calls == 1
    assert child.model_calls == 1
    assert parent.agent() is child
    assert parent.agent().model_calls == 1


@pytest.mark.parametrize("cap", [0, 1, 4])
def test_agent_model_limit_does_not_consume_rejected_call(cap: int) -> None:
    parent = Budget(max_model_calls=10)
    child = AgentBudget(parent, cap, 4, 30)
    for _ in range(cap):
        child.take_model_call("scope")
    with pytest.raises(BudgetExceeded, match="AGENT_MODEL_CALLS"):
        child.take_model_call("overflow")
    assert parent.model_calls == child.model_calls == cap
    assert parent.stop_reason == child.stop_reason == "AGENT_MODEL_CALLS"


def test_parent_limit_also_limits_agent() -> None:
    parent = Budget(max_model_calls=1)
    parent.take_model_call("extract")
    child = AgentBudget(parent, 10, 16, 75)
    with pytest.raises(BudgetExceeded, match="MODEL_CALL_LIMIT"):
        child.take_model_call("scope")
    assert child.model_calls == 0
    assert parent.model_calls == 1


def test_agent_tool_cap_debits_parent_once() -> None:
    parent = Budget(max_tool_calls=5)
    child = AgentBudget(parent, 10, 1, 75)
    child.take_tool("read_passage")
    with pytest.raises(BudgetExceeded, match="AGENT_TOOL_CALLS"):
        child.take_tool("read_passage")
    assert parent.tool_calls == child.tool_calls == 1


@pytest.mark.parametrize("parent_seconds,child_seconds,reason", [(10, 30, "RUN_DEADLINE"), (30, 10, "AGENT_DEADLINE")])
def test_earliest_deadline_stops_agent_without_sleep(parent_seconds: int, child_seconds: int, reason: str) -> None:
    clock = Clock()
    parent = Budget(deadline_s=parent_seconds, _clock=clock)
    child = AgentBudget(parent, 10, 10, child_seconds)
    clock.now += 10
    assert child.remaining_s() == 0
    with pytest.raises(BudgetExceeded, match=reason):
        child.take_model_call("scope")
    assert parent.model_calls == child.model_calls == 0
    assert parent.stop_reason == reason


def test_budget_stop_reason_is_sticky_across_call_types() -> None:
    parent = Budget(max_model_calls=0)
    with pytest.raises(BudgetExceeded, match="MODEL_CALL_LIMIT"):
        parent.take_model_call("extract")
    with pytest.raises(BudgetExceeded, match="MODEL_CALL_LIMIT"):
        parent.take_tool("read")
    assert parent.tool_calls == 0


@pytest.mark.parametrize("seconds", [float("nan"), float("inf"), -1])
def test_nonfinite_or_negative_deadline_rejected(seconds: float) -> None:
    with pytest.raises(ValueError):
        Budget(deadline_s=seconds)
