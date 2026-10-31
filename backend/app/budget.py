"""P2-owned S0 budget implementation; P2 completes run/agent accounting at S1."""
from __future__ import annotations

from dataclasses import dataclass, field
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

    @classmethod
    def from_settings(cls) -> Budget:
        s = config.settings
        return cls(s.run_max_model_calls, s.agent_max_tool_calls, s.run_deadline_s)

    @property
    def stop_reason(self) -> str | None:
        return self._stop_reason

    def remaining_s(self) -> float:
        return max(0.0, self.deadline_s - (monotonic() - self._started_at))

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
            "seconds": {"used": monotonic() - self._started_at, "cap": self.deadline_s},
        }
