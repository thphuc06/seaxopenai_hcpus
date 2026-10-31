"""P2-owned S0 budget implementation; P2 completes run/agent accounting at S1."""
from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Callable
import math
from time import monotonic

from app import config


class BudgetExceeded(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass
class Budget:
    max_model_calls: int = 24
    max_tool_calls: int = 16
    deadline_s: float = 120.0
    model_calls: int = 0
    tool_calls: int = 0
    _started_at: float = field(default_factory=monotonic, repr=False)
    _stop_reason: str | None = None
    _clock: Callable[[], float] = field(default=monotonic, repr=False)
    _agent_budget: AgentBudget | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.max_model_calls < 0 or self.max_tool_calls < 0 or not math.isfinite(self.deadline_s) or self.deadline_s < 0:
            raise ValueError("Budget caps must be finite and nonnegative")
        self._started_at = self._clock()

    @classmethod
    def from_settings(cls) -> Budget:
        s = config.settings
        return cls(s.run_max_model_calls, s.agent_max_tool_calls, s.run_deadline_s)

    @property
    def stop_reason(self) -> str | None:
        return self._stop_reason

    def remaining_s(self) -> float:
        return max(0.0, self.deadline_s - (self._clock() - self._started_at))

    def _check(self, used: int, cap: int, reason: str) -> None:
        if self._stop_reason:
            raise BudgetExceeded(self._stop_reason)
        if self.remaining_s() <= 0:
            self._stop_reason = "RUN_DEADLINE"
        elif used >= cap:
            self._stop_reason = reason
        if self._stop_reason:
            raise BudgetExceeded(self._stop_reason)

    def take_model_call(self, step: str) -> None:
        self._check(self.model_calls, self.max_model_calls, "MODEL_CALL_LIMIT")
        self.model_calls += 1

    def take_tool(self, name: str) -> None:
        self._check(self.tool_calls, self.max_tool_calls, "TOOL_CALL_LIMIT")
        self.tool_calls += 1

    def usage(self) -> dict[str, dict[str, int | float]]:
        return {
            "model_calls": {"used": self.model_calls, "cap": self.max_model_calls},
            "tool_calls": {"used": self.tool_calls, "cap": self.max_tool_calls},
            "seconds": {"used": self._clock() - self._started_at, "cap": self.deadline_s},
        }

    def agent(self) -> AgentBudget:
        """Return the same child budget for the whole run; never reset counters."""
        if self._agent_budget is None:
            settings = config.settings
            self._agent_budget = AgentBudget(
                self, settings.agent_max_model_calls, settings.agent_max_tool_calls,
                settings.agent_deadline_s,
            )
        return self._agent_budget


@dataclass
class AgentBudget:
    """Agent-local limits debit the original run before permitting a side effect."""

    parent: Budget
    max_model_calls: int
    max_tool_calls: int
    deadline_s: float
    model_calls: int = 0
    tool_calls: int = 0
    _started_at: float = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.max_model_calls < 0 or self.max_tool_calls < 0 or not math.isfinite(self.deadline_s) or self.deadline_s < 0:
            raise ValueError("Agent budget caps must be finite and nonnegative")
        self._started_at = self.parent._clock()

    @property
    def stop_reason(self) -> str | None:
        return self.parent.stop_reason

    def remaining_s(self) -> float:
        own_remaining = self.deadline_s - (self.parent._clock() - self._started_at)
        return max(0.0, min(own_remaining, self.parent.remaining_s()))

    def _check(self, used: int, cap: int, reason: str) -> None:
        if self.parent.stop_reason:
            raise BudgetExceeded(self.parent.stop_reason)
        if self.parent.remaining_s() <= 0:
            self.parent._stop_reason = "RUN_DEADLINE"
        elif self.remaining_s() <= 0:
            self.parent._stop_reason = "AGENT_DEADLINE"
        elif used >= cap:
            self.parent._stop_reason = reason
        if self.parent.stop_reason:
            raise BudgetExceeded(self.parent.stop_reason)

    def take_model_call(self, step: str) -> None:
        self._check(self.model_calls, self.max_model_calls, "AGENT_MODEL_CALLS")
        self.parent.take_model_call(step)
        self.model_calls += 1

    def take_tool(self, name: str) -> None:
        self._check(self.tool_calls, self.max_tool_calls, "AGENT_TOOL_CALLS")
        self.parent.take_tool(name)
        self.tool_calls += 1

    def usage(self) -> dict[str, dict[str, int | float]]:
        return {
            "model_calls": {"used": self.model_calls, "cap": self.max_model_calls},
            "tool_calls": {"used": self.tool_calls, "cap": self.max_tool_calls},
            "seconds": {"used": self.parent._clock() - self._started_at, "cap": self.deadline_s},
        }
