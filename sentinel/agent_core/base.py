"""Shared dataclasses and interfaces for Agent Core."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from sentinel.planning.task_graph import TaskNode
    from sentinel.simulation.sandbox import SimulationResult
    from sentinel.policy.policy_engine import PolicyResult


@dataclass
class PlanStep:
    """A deterministic step in a plan."""

    step_id: int
    description: str
    tool_name: Optional[str] = None
    params: Dict[str, Any] = field(default_factory=dict)
    expected_output: Optional[str] = None
    depends_on: List[int] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


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

    deterministic: bool

    def __init__(self, name: str, description: str = "", deterministic: bool = True) -> None:
        self.name = name
        self.description = description or name
        self.deterministic = deterministic

    def __call__(self, **kwargs: Any) -> Any:  # pragma: no cover - thin wrapper
        return self.execute(**kwargs)

    def execute(self, **kwargs: Any) -> Any:  # pragma: no cover - abstract
        """Run the tool with the provided keyword arguments."""

        raise NotImplementedError("Tool subclasses must implement execute()")


@dataclass
class ExecutionResult:
    """Execution result for a single task node."""

    node: "TaskNode"
    success: bool
    output: Any = None
    error: Optional[str] = None
    attempted_recovery: bool = False
    simulation: Optional["SimulationResult"] = None
    policy: Optional["PolicyResult"] = None


@dataclass
class ExecutionTrace:
    """Ordered results from a task graph execution."""

    results: List[ExecutionResult] = field(default_factory=list)
    batches: List[List[str]] = field(default_factory=list)

    def add(self, result: ExecutionResult) -> None:
        self.results.append(result)

    def add_batch(self, batch: List[str]) -> None:
        self.batches.append(batch)

    @property
    def failed_nodes(self) -> List[ExecutionResult]:
        return [res for res in self.results if not res.success]

    def summary(self) -> str:
        parts = []
        for idx, res in enumerate(self.results, start=1):
            if res.success:
                parts.append(f"Task {res.node.id} ok: {res.output}")
            else:
                recovery_note = " (after recovery)" if res.attempted_recovery else ""
                parts.append(
                    f"Task {res.node.id} failed{recovery_note}: {res.error}"
                )
            if res.simulation and res.simulation.warnings:
                parts.append(
                    f"Simulated warnings for {res.node.id}: {', '.join(res.simulation.warnings)}"
                )
            if res.policy and not res.policy.allowed:
                parts.append(
                    f"Policy blocked {res.node.id}: {'; '.join(res.policy.reasons)}"
                )
        batches_repr = (
            f" | batches={','.join('[' + ','.join(batch) + ']' for batch in self.batches)}"
            if self.batches
            else ""
        )
        return " | ".join(parts) + batches_repr
