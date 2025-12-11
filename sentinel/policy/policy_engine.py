"""Policy engine governing planning and execution safety and preferences."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from sentinel.logging.logger import get_logger
from sentinel.memory.memory_manager import MemoryManager
from sentinel.planning.task_graph import TaskGraph, TaskNode
from sentinel.tools.registry import ToolRegistry

logger = get_logger(__name__)


@dataclass
class PolicyDecision:
    allowed: bool
    reason: str
    details: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"allowed": self.allowed, "reason": self.reason, "details": self.details or {}}


class PolicyEngine:
    """Apply safety, preference, and execution policies across the agent."""

    def __init__(
        self,
        memory: MemoryManager,
        allowed_permissions: Optional[Set[str]] = None,
        deterministic_first: bool = True,
        parallel_limit: int = 3,
    ) -> None:
        self.memory = memory
        self.allowed_permissions = allowed_permissions or {"read", "analyze", "search", "generate"}
        self.deterministic_first = deterministic_first
        self.parallel_limit = parallel_limit

    # ------------------------------------------------------------------
    # Plan-time policies
    # ------------------------------------------------------------------
    def evaluate_plan(self, graph: TaskGraph, registry: ToolRegistry) -> None:
        self._check_metadata(graph, registry)
        self._enforce_parallel_limit(graph)
        self._check_artifacts(graph)

    def _check_metadata(self, graph: TaskGraph, registry: ToolRegistry) -> None:
        for node in graph:
            if node.tool is None:
                continue
            schema = registry.get_schema(node.tool)
            if schema is None:
                self._record_event("block", f"Tool metadata missing for {node.tool}")
                raise PermissionError(f"Tool metadata missing for {node.tool}")
            if not set(schema.permissions).issubset(self.allowed_permissions):
                self._record_event(
                    "block",
                    f"Permissions not allowed for {node.tool}",
                    {"permissions": schema.permissions},
                )
                raise PermissionError(f"Tool '{node.tool}' permissions not allowed")
            if self.deterministic_first and not schema.deterministic:
                node.parallelizable = False

    def _enforce_parallel_limit(self, graph: TaskGraph) -> None:
        parallel_count = sum(1 for node in graph if node.parallelizable)
        if parallel_count > self.parallel_limit:
            self._record_event(
                "rewrite",
                "Parallel limit exceeded; serializing tasks",
                {"parallel_count": parallel_count, "limit": self.parallel_limit},
            )
            for node in graph:
                node.parallelizable = False

    def _check_artifacts(self, graph: TaskGraph) -> None:
        produced: Set[str] = set()
        for node in graph:
            overlap = produced.intersection(set(node.produces))
            if overlap:
                self._record_event("block", f"Artifact collision detected: {', '.join(overlap)}")
                raise ValueError(f"Artifact collision detected: {', '.join(overlap)}")
            produced.update(node.produces)

    # ------------------------------------------------------------------
    # Execution-time policies
    # ------------------------------------------------------------------
    def validate_execution(self, node: TaskNode, registry: ToolRegistry) -> None:
        if node.tool is None:
            return
        schema = registry.get_schema(node.tool)
        if schema is None:
            raise PermissionError(f"Cannot execute tool {node.tool} without metadata")
        dangerous_args = [arg for arg in node.args.values() if isinstance(arg, str) and self._is_dangerous(arg)]
        if dangerous_args:
            self._record_event("block", f"Unsafe arguments for {node.id}", {"args": dangerous_args})
            raise PermissionError(f"Unsafe arguments detected for task {node.id}")

    def _is_dangerous(self, value: str) -> bool:
        forbidden = ["subprocess", "os.system", "rm -rf", "../", "\\..\\"]
        return any(token in value for token in forbidden)

    # ------------------------------------------------------------------
    # Reflection-time policies
    # ------------------------------------------------------------------
    def advise(self, issues: List[str]) -> PolicyDecision:
        if not issues:
            return PolicyDecision(True, "no issues")
        return PolicyDecision(False, "issues_detected", {"issues": issues})

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
    def _record_event(self, event_type: str, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        payload = {"event": event_type, "message": message, "details": details or {}}
        try:
            self.memory.store_text(str(payload), namespace="policy_events", metadata=payload)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to persist policy event: %s", exc)

