"""Shared dataclasses and interfaces for Agent Core."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PlanStep:
    """A deterministic step in a plan."""

    step_id: int
    description: str
    tool_name: Optional[str] = None
    params: Dict[str, Any] = field(default_factory=dict)
    expected_output: Optional[str] = None


@dataclass
class Plan:
    steps: List[PlanStep]


class Tool:
    """Base class for all tools executed by Sentinel.

    Tools are intentionally minimal and deterministic. Subclasses should
    implement :py:meth:`execute` and avoid side effects so that execution can be
    replayed safely inside the sandbox.
    """

    name: str
    description: str

    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description or name

    def __call__(self, **kwargs: Any) -> Any:  # pragma: no cover - thin wrapper
        return self.execute(**kwargs)

    def execute(self, **kwargs: Any) -> Any:  # pragma: no cover - abstract
        """Run the tool with the provided keyword arguments."""

        raise NotImplementedError("Tool subclasses must implement execute()")


@dataclass
class ExecutionResult:
    step: PlanStep
    success: bool
    output: Any = None
    error: Optional[str] = None


@dataclass
class ExecutionTrace:
    results: List[ExecutionResult] = field(default_factory=list)

    def add(self, result: ExecutionResult) -> None:
        self.results.append(result)

    def summary(self) -> str:
        parts = []
        for res in self.results:
            if res.success:
                parts.append(f"Step {res.step.step_id}: {res.output}")
            else:
                parts.append(f"Step {res.step.step_id} failed: {res.error}")
        return " | ".join(parts)
