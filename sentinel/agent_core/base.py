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
