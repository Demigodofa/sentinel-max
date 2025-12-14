"""Policy engine governing planning and execution safety and preferences."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

from sentinel.config.sandbox_config import get_sandbox_root
from sentinel.logging.logger import get_logger
from sentinel.memory.memory_manager import MemoryManager
from sentinel.tools.registry import ToolRegistry

if TYPE_CHECKING:  # pragma: no cover - avoid circular imports at runtime
    from sentinel.planning.task_graph import TaskGraph, TaskNode

logger = get_logger(__name__)


class PolicyViolation(Exception):
    """Raised when a project violates MAX system policy rules."""


@dataclass
class PolicyResult:
    """Structured response describing policy evaluation outcomes."""

    allowed: bool
    reasons: List[str] = field(default_factory=list)
    rewrites: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def merge(self, other: "PolicyResult") -> "PolicyResult":
        return PolicyResult(
            allowed=self.allowed and other.allowed,
            reasons=self.reasons + other.reasons,
            rewrites=self.rewrites + other.rewrites,
            details={**self.details, **other.details},
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reasons": self.reasons,
            "rewrites": self.rewrites,
            "details": self.details,
        }


class PolicyEngine:
    """Apply safety, preference, and execution policies across the agent."""

    def __init__(
        self,
        memory: MemoryManager | None = None,
        allowed_permissions: Optional[Set[str]] = None,
        deterministic_first: bool = True,
        parallel_limit: int = 3,
        max_execution_time: float | None = None,
        max_cycles: int | None = None,
        max_consecutive_failures: int = 3,
        real_tool_allowlist: Optional[Set[str]] = None,
        approval_required: bool = True,
        max_research_depth: int = 3,
        max_documents_per_cycle: int = 15,
        approved_domains: Optional[Set[str]] = None,
        max_goals: int = 50,
        max_dependency_depth: int = 20,
        max_project_duration_days: int = 14,
        max_refinement_rounds: int = 25,
        forbidden_keywords: Optional[list[str]] = None,
    ) -> None:
        self.memory = memory
        self.allowed_permissions = allowed_permissions or {"read", "analyze", "search", "generate"}
        self.deterministic_first = deterministic_first
        self.parallel_limit = parallel_limit
        self.max_execution_time = max_execution_time
        self.max_cycles = max_cycles
        self.max_consecutive_failures = max_consecutive_failures
        self.real_tool_allowlist = real_tool_allowlist
        self.approval_required = approval_required
        self.max_research_depth = max_research_depth
        self.max_documents_per_cycle = max_documents_per_cycle
        self.approved_domains = approved_domains or {"research", "automation", "coding", "web tasks"}
        self.max_goals = max_goals
        self.max_dependency_depth = max_dependency_depth
        self.max_project_duration_days = max_project_duration_days
        self.max_refinement_rounds = max_refinement_rounds
        self.forbidden_keywords = forbidden_keywords or [
            "exploit",
            "bypass security",
            "privilege escalation",
            "harm",
        ]
        self.correlation_id: str | None = None

    def assert_path_in_sandbox(self, path: str) -> None:
        """
        Blocks ANY file op outside SENTINEL_SANDBOX_ROOT.
        """
        root = get_sandbox_root().resolve()
        target = Path(path).expanduser().resolve()
        if root != target and root not in target.parents:
            raise PermissionError(f"Path '{target}' is outside sandbox root '{root}'")

    # ------------------------------------------------------------------
    # Plan-time policies
    # ------------------------------------------------------------------
    def evaluate_plan(
        self, graph: "TaskGraph", registry: ToolRegistry, enforce: bool = True
    ) -> PolicyResult:
        """
        Validate a task graph against policy rules.

        When ``enforce`` is True (default), a ``PermissionError`` is raised if the
        plan violates policy. Callers can set ``enforce=False`` to receive a
        ``PolicyResult`` while allowing the program to continue (useful for
        testing or advisory-only flows).
        """

        checks: list[PolicyResult] = [
            self._check_metadata(graph, registry),
            self._enforce_parallel_limit(graph),
            self._check_artifacts(graph),
        ]

        result = PolicyResult(allowed=True)
        for check in checks:
            result = result.merge(check)

        event_type = "allow" if result.allowed else "block"
        payload: Dict[str, Any] = {
            "nodes": len(list(graph)),
            "parallel_limit": self.parallel_limit,
        }
        if result.reasons:
            payload["reasons"] = result.reasons
        if result.rewrites:
            payload["rewrites"] = result.rewrites
        self._record_event(event_type, "Plan validated", payload)

        if enforce and not result.allowed:
            raise PermissionError("; ".join(result.reasons))

        return result

    def _check_metadata(self, graph: TaskGraph, registry: ToolRegistry) -> None:
        result = PolicyResult(allowed=True)
        for node in graph:
            if node.tool is None:
                continue
            schema = registry.get_schema(node.tool)
            if schema is None:
                self._record_event("block", f"Tool metadata missing for {node.tool}")
                result.allowed = False
                result.reasons.append(f"Tool metadata missing for {node.tool}")
                continue
            if not set(schema.permissions).issubset(self.allowed_permissions):
                self._record_event(
                    "block",
                    f"Permissions not allowed for {node.tool}",
                    {"permissions": schema.permissions},
                )
                result.allowed = False
                result.reasons.append(f"Tool '{node.tool}' permissions not allowed")
            if self.deterministic_first and not schema.deterministic:
                node.parallelizable = False
        return result

    def _enforce_parallel_limit(self, graph: TaskGraph) -> PolicyResult:
        result = PolicyResult(allowed=True)
        parallel_count = sum(1 for node in graph if node.parallelizable)
        if parallel_count > self.parallel_limit:
            self._record_event(
                "rewrite",
                "Parallel limit exceeded; serializing tasks",
                {"parallel_count": parallel_count, "limit": self.parallel_limit},
            )
            for node in graph:
                node.parallelizable = False
            result.rewrites.append("Parallel limit exceeded; tasks serialized")
        return result

    def _check_artifacts(self, graph: TaskGraph) -> PolicyResult:
        result = PolicyResult(allowed=True)
        produced: Set[str] = set()
        for node in graph:
            overlap = produced.intersection(set(node.produces))
            if overlap:
                message = f"Artifact collision detected: {', '.join(overlap)}"
                self._record_event("block", message)
                result.allowed = False
                result.reasons.append(message)
            produced.update(node.produces)
        return result

    # ------------------------------------------------------------------
    # Execution-time policies
    # ------------------------------------------------------------------
    def check_execution_allowed(self, tool_name: str, enforce: bool = True) -> PolicyResult:
        result = PolicyResult(allowed=True)
        if self.real_tool_allowlist is not None and tool_name not in self.real_tool_allowlist:
            message = f"Tool {tool_name} not allowed for real execution"
            self._record_event("block", message)
            result.allowed = False
            result.reasons.append(message)
        if enforce and not result.allowed:
            raise PermissionError("; ".join(result.reasons))
        return result

    def check_runtime_limits(self, context: Dict[str, Any], enforce: bool = True) -> PolicyResult:
        result = PolicyResult(allowed=True)
        elapsed = context.get("elapsed")
        cycles = context.get("cycles", 0)
        consecutive_failures = context.get("consecutive_failures", 0)
        if self.max_execution_time is not None and elapsed is not None and elapsed > self.max_execution_time:
            self._record_event("block", "Max execution time exceeded", {"elapsed": elapsed})
            result.allowed = False
            result.reasons.append("Max execution time exceeded")
        if self.max_cycles is not None and cycles >= self.max_cycles:
            self._record_event("block", "Max cycles reached", {"cycles": cycles})
            result.allowed = False
            result.reasons.append("Max cycles reached")
        if self.max_consecutive_failures is not None and consecutive_failures > self.max_consecutive_failures:
            self._record_event(
                "block",
                "Consecutive failure limit exceeded",
                {"consecutive_failures": consecutive_failures},
            )
            result.allowed = False
            result.reasons.append("Consecutive failure limit exceeded")
        if enforce and not result.allowed:
            raise RuntimeError("; ".join(result.reasons))
        return result

    def validate_execution(
        self, node: "TaskNode", registry: ToolRegistry, enforce: bool = True
    ) -> PolicyResult:
        if node.tool is None:
            return PolicyResult(allowed=True)
        schema = registry.get_schema(node.tool)
        if schema is None:
            result = PolicyResult(False, [f"Cannot execute tool {node.tool} without metadata"])
            if enforce:
                raise PermissionError(result.reasons[0])
            return result
        dangerous_args = [arg for arg in node.args.values() if isinstance(arg, str) and self._is_dangerous(arg)]
        if dangerous_args:
            message = f"Unsafe arguments for {node.id}"
            self._record_event("block", message, {"args": dangerous_args})
            result = PolicyResult(False, [message], details={"args": dangerous_args})
            if enforce:
                raise PermissionError(f"Unsafe arguments detected for task {node.id}")
            return result
        return PolicyResult(allowed=True)

    def _is_dangerous(self, value: str) -> bool:
        forbidden = ["subprocess", "os.system", "rm -rf", "../", "\\..\\"]
        return any(token in value for token in forbidden)

    # ------------------------------------------------------------------
    # Reflection-time policies
    # ------------------------------------------------------------------
    def advise(self, issues: List[str]) -> PolicyResult:
        if not issues:
            return PolicyResult(True, reasons=["no issues"])
        return PolicyResult(False, reasons=["issues_detected"], details={"issues": issues})

    # ------------------------------------------------------------------
    # Research-time policies
    # ------------------------------------------------------------------
    def check_research_limits(self, query, depth, enforce: bool = True) -> PolicyResult:
        result = PolicyResult(allowed=True)
        if depth > self.max_research_depth:
            self._record_event("block", "Research depth exceeded", {"depth": depth})
            result.allowed = False
            result.reasons.append("Research depth exceeded")
        if not str(query).strip():
            if enforce:
                raise ValueError("Query must be non-empty for research")
            result.allowed = False
            result.reasons.append("Query must be non-empty for research")
        if result.allowed:
            self._record_event("allow", "Research limits validated", {"depth": depth, "query": query})
        if enforce and not result.allowed:
            raise PermissionError("; ".join(result.reasons))
        return result

    def validate_semantic_updates(self, semantic_profiles, enforce: bool = True) -> PolicyResult:
        result = PolicyResult(allowed=True)
        if not isinstance(semantic_profiles, dict):
            if enforce:
                raise ValueError("Semantic profiles must be a dictionary")
            result.allowed = False
            result.reasons.append("Semantic profiles must be a dictionary")
            return result
        disallowed = [name for name in semantic_profiles if ":" in name and name.split(":")[0] not in self.approved_domains]
        if disallowed:
            self._record_event(
                "block",
                "Semantic update domain not approved",
                {"tools": disallowed},
            )
            result.allowed = False
            result.reasons.append("Semantic update domain not approved")
        else:
            self._record_event(
                "allow",
                "Semantic profiles validated",
                {"count": len(semantic_profiles)},
            )
        if enforce and not result.allowed:
            raise PermissionError("; ".join(result.reasons))
        return result

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
    def attach_correlation_id(self, correlation_id: str | None) -> None:
        """Set the correlation ID used for recorded policy events."""

        self.correlation_id = correlation_id

    def _record_event(self, event_type: str, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        payload = {
            "event": event_type,
            "message": message,
            "details": details or {},
            "correlation_id": self.correlation_id,
        }
        try:
            if self.memory is not None:
                self.memory.store_text(
                    str(payload),
                    namespace="policy_events",
                    metadata=payload,
                )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to persist policy event: %s", exc)

    def record_event(self, event_type: str, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Public helper to capture policy events from other subsystems."""

        self._record_event(event_type, message, details)

    # ------------------------------------------------------------------
    # Long-horizon project governance
    # ------------------------------------------------------------------
    def check_project_limits(self, project_data: Dict[str, Any]) -> None:
        goals = project_data.get("goals", [])
        if len(goals) > self.max_goals:
            raise PolicyViolation(
                f"Project has {len(goals)} goals, exceeds limit {self.max_goals}"
            )

    def validate_project_plan(self, plan: Dict[str, Any]) -> None:
        """
        Validate dependency depth + forbidden actions.
        Plan is project_engine.build_long_horizon_plan(project_id)
        """

        dependencies = plan.get("dependencies", {})
        max_depth = self._max_dependency_depth(dependencies)

        if max_depth > self.max_dependency_depth:
            raise PolicyViolation(
                f"Dependency graph depth {max_depth} exceeds limit {self.max_dependency_depth}"
            )

        for step in plan.get("steps", []):
            action = step.get("action", "").lower()
            for bad in self.forbidden_keywords:
                if bad in action:
                    raise PolicyViolation(
                        f"Forbidden action detected in plan: '{action}'"
                    )

    def enforce_autonomy_constraints(self, project_id: str, state: Dict[str, Any]) -> None:
        """
        Called before each autonomous cycle.
        Prevents runaway execution.
        """

        rounds = state.get("refinement_rounds", 0)
        if rounds > self.max_refinement_rounds:
            raise PolicyViolation(
                f"Project {project_id} exceeded refinement limit: {rounds}"
            )

        days = state.get("project_age_days", 0)
        if days > self.max_project_duration_days:
            raise PolicyViolation(
                f"Project age {days} days exceeds limit {self.max_project_duration_days}"
            )

    def _max_dependency_depth(self, dependencies: Dict[str, Any]) -> int:
        def extract_depth(value: Any) -> int:
            if isinstance(value, dict) and "depth" in value:
                return int(value.get("depth", 0))
            return 0

        explicit_depths = [extract_depth(value) for value in dependencies.values()]
        if any(depth > 0 for depth in explicit_depths):
            return max(explicit_depths) if explicit_depths else 0

        depths: Dict[str, int] = {}
        visiting: Set[str] = set()

        def dfs(node: str) -> int:
            if node in depths:
                return depths[node]
            if node in visiting:
                raise PolicyViolation(f"Cycle detected in dependency graph at {node}")
            visiting.add(node)
            deps = dependencies.get(node, [])
            if isinstance(deps, dict):
                deps = deps.get("depends_on", [])
            if not isinstance(deps, list):
                raise PolicyViolation(f"Invalid dependency format for {node}")
            depth = 0 if not deps else 1 + max(dfs(dep) for dep in deps)
            visiting.remove(node)
            depths[node] = depth
            return depth

        for node in dependencies:
            dfs(node)
        return max(depths.values()) if depths else 0
