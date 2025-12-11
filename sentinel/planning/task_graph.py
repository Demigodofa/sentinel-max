"""Task graph planning and execution utilities."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from sentinel.agent_core.base import ExecutionResult, ExecutionTrace
from sentinel.agent_core.sandbox import Sandbox
from sentinel.logging.logger import get_logger
from sentinel.tools.registry import ToolRegistry

logger = get_logger(__name__)


@dataclass
class TaskNode:
    """Single task in a task graph."""

    id: str
    description: str
    tool: str | None
    args: Dict[str, Any] = field(default_factory=dict)
    requires: List[str] = field(default_factory=list)
    produces: List[str] = field(default_factory=list)
    parallelizable: bool = False


class TaskGraph:
    """DAG container for :class:`TaskNode` definitions."""

    def __init__(
        self, nodes: Optional[Iterable[TaskNode]] = None, metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        self.nodes: Dict[str, TaskNode] = {}
        self.metadata: Dict[str, Any] = metadata or {}
        for node in nodes or []:
            self.add_node(node)

    def add_node(self, node: TaskNode) -> None:
        if node.id in self.nodes:
            raise ValueError(f"Duplicate task id detected: {node.id}")
        self.nodes[node.id] = node

    def get(self, node_id: str) -> TaskNode:
        return self.nodes[node_id]

    def __iter__(self):
        return iter(self.nodes.values())

    def add_metadata(self, **metadata: Any) -> None:
        self.metadata.update(metadata)

    def signature(self) -> Tuple[Tuple[str, Tuple[str, ...], Tuple[str, ...]], ...]:
        """Compact signature for repeat-plan detection."""

        ordered = []
        for node in sorted(self.nodes.values(), key=lambda n: n.id):
            ordered.append(
                (
                    node.id,
                    tuple(sorted(node.requires)),
                    tuple(sorted(node.produces)),
                )
            )
        return tuple(ordered)


class GraphValidator:
    """Validate :class:`TaskGraph` objects for DAG correctness."""

    def __init__(self, tool_registry: ToolRegistry) -> None:
        self.tool_registry = tool_registry

    def validate(self, graph: TaskGraph, available_inputs: Optional[Set[str]] = None) -> None:
        available_inputs = available_inputs or set()
        self._validate_dependencies_exist(graph)
        self._validate_no_cycles(graph)
        self._validate_tools(graph)
        self._validate_requires(graph, available_inputs)
        self._validate_args(graph)

    def _dependency_map(self, graph: TaskGraph) -> Dict[str, Set[str]]:
        produced: Dict[str, str] = {}
        for node in graph:
            for artifact in node.produces:
                if artifact in produced:
                    raise ValueError(f"Artifact '{artifact}' produced by multiple tasks")
                produced[artifact] = node.id

        dep_map: Dict[str, Set[str]] = {node.id: set() for node in graph}
        for node in graph:
            for requirement in node.requires:
                if requirement in produced:
                    dep_map[node.id].add(produced[requirement])
        return dep_map

    def _validate_dependencies_exist(self, graph: TaskGraph) -> None:
        produced: Set[str] = set()
        for node in graph:
            produced.update(node.produces)
        for node in graph:
            for requirement in node.requires:
                if requirement not in produced:
                    raise ValueError(
                        f"Task '{node.id}' requires '{requirement}' which no task produces"
                    )

    def _validate_no_cycles(self, graph: TaskGraph) -> None:
        dependencies = self._dependency_map(graph)
        visited: Set[str] = set()
        stack: Set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in stack:
                raise ValueError(f"Cycle detected involving '{node_id}'")
            if node_id in visited:
                return
            visited.add(node_id)
            stack.add(node_id)
            for dep in dependencies[node_id]:
                visit(dep)
            stack.remove(node_id)

        for node_id in dependencies:
            visit(node_id)

    def _validate_tools(self, graph: TaskGraph) -> None:
        for node in graph:
            if node.tool is None:
                continue
            if not self.tool_registry.has_tool(node.tool):
                raise ValueError(f"Task '{node.id}' references unknown tool '{node.tool}'")
            schema = self.tool_registry.get_schema(node.tool)
            if schema is None:
                raise ValueError(f"Tool '{node.tool}' is missing metadata schema")

    def _validate_requires(self, graph: TaskGraph, available_inputs: Set[str]) -> None:
        produced: Set[str] = set(available_inputs)
        for node in graph:
            produced.update(node.produces)
        for node in graph:
            for requirement in node.requires:
                if requirement not in produced:
                    raise ValueError(
                        f"Dangling requirement '{requirement}' for task '{node.id}'"
                    )

    def _validate_args(self, graph: TaskGraph) -> None:
        for node in graph:
            if node.tool is None:
                continue
            schema = self.tool_registry.get_schema(node.tool)
            if not schema:
                continue
            required_fields = [
                key
                for key, meta in schema.input_schema.items()
                if meta.get("required", False)
            ]
            for field in required_fields:
                if field not in node.args:
                    raise ValueError(
                        f"Task '{node.id}' missing required argument '{field}' for tool '{node.tool}'"
                    )


class TopologicalExecutor:
    """Execute a :class:`TaskGraph` respecting dependencies."""

    def __init__(
        self,
        registry: ToolRegistry,
        sandbox: Sandbox,
        memory=None,
        validator: GraphValidator | None = None,
        policy_engine=None,
    ) -> None:
        self.registry = registry
        self.sandbox = sandbox
        self.memory = memory
        self.validator = validator or GraphValidator(registry)
        self.policy_engine = policy_engine

    def execute(self, graph: TaskGraph, available_inputs: Optional[Dict[str, Any]] = None) -> ExecutionTrace:
        available_inputs = available_inputs or {}
        self.validator.validate(graph, set(available_inputs))
        produced_by = self._build_produced_map(graph)
        dependencies = self._build_dependency_graph(graph, produced_by)
        indegree = {node_id: len(deps) for node_id, deps in dependencies.items()}

        ready: List[str] = [node_id for node_id, deg in indegree.items() if deg == 0]
        executed: Set[str] = set()
        failed: Set[str] = set()
        artifacts: Dict[str, Any] = dict(available_inputs)
        trace = ExecutionTrace()

        while ready:
            batch = self._next_batch(graph, ready)
            trace.add_batch(batch)
            logger.info("Executing batch: %s", batch)
            for node_id in batch:
                ready.remove(node_id)
                node = graph.get(node_id)
                if any(dep in failed for dep in dependencies[node_id]):
                    error = f"Dependencies failed for task {node.id}"
                    result = ExecutionResult(node=node, success=False, error=error)
                    trace.add(result)
                    failed.add(node.id)
                    continue

                args = self._resolve_args(node, artifacts)
                if self.policy_engine:
                    try:
                        self.policy_engine.validate_execution(node, self.registry)
                    except Exception as exc:  # pragma: no cover - defensive safety
                        result = ExecutionResult(node=node, success=False, error=str(exc))
                        failed.add(node.id)
                        trace.add(result)
                        if self.memory:
                            self._record_memory(result)
                        self._update_neighbors(node.id, dependencies, indegree, ready)
                        continue
                result = self._run_with_recovery(node, args)
                if result.success:
                    executed.add(node.id)
                    self._store_outputs(node, result.output, artifacts)
                else:
                    failed.add(node.id)
                trace.add(result)
                if self.memory:
                    self._record_memory(result)
                self._update_neighbors(node.id, dependencies, indegree, ready)

        remaining = set(graph.nodes) - executed - failed
        for node_id in remaining:
            result = ExecutionResult(
                node=graph.get(node_id),
                success=False,
                error="Skipped due to unresolved dependencies",
            )
            trace.add(result)
            if self.memory:
                self._record_memory(result)

        return trace

    def _build_produced_map(self, graph: TaskGraph) -> Dict[str, str]:
        produced: Dict[str, str] = {}
        for node in graph:
            for artifact in node.produces:
                produced[artifact] = node.id
        return produced

    def _build_dependency_graph(
        self, graph: TaskGraph, produced_by: Dict[str, str]
    ) -> Dict[str, Set[str]]:
        deps: Dict[str, Set[str]] = {node.id: set() for node in graph}
        for node in graph:
            for requirement in node.requires:
                producer = produced_by.get(requirement)
                if producer:
                    deps[node.id].add(producer)
        return deps

    def _next_batch(self, graph: TaskGraph, ready: List[str]) -> List[str]:
        batch: List[str] = []
        for node_id in list(ready):
            node = graph.get(node_id)
            if not node.parallelizable and batch:
                continue
            batch.append(node_id)
            if not node.parallelizable:
                break
        if not batch:
            batch.append(ready[0])
        return batch

    def _resolve_args(self, node: TaskNode, artifacts: Dict[str, Any]) -> Dict[str, Any]:
        args = dict(node.args)
        for requirement in node.requires:
            if requirement not in args and requirement in artifacts:
                args[requirement] = artifacts[requirement]
        return args

    def _execute_node(self, node: TaskNode, args: Dict[str, Any]) -> Any:
        if node.tool is None:
            return args or node.description
        return self.sandbox.execute(self.registry.call, node.tool, **args)

    def _run_with_recovery(self, node: TaskNode, args: Dict[str, Any]) -> ExecutionResult:
        try:
            output = self._execute_node(node, args)
            return ExecutionResult(node=node, success=True, output=output)
        except Exception as exc:  # pragma: no cover - runtime failures are expected
            logger.error("Task %s failed: %s", node.id, exc)
            try:
                retry_output = self._execute_node(node, args)
                return ExecutionResult(
                    node=node, success=True, output=retry_output, attempted_recovery=True
                )
            except Exception as retry_exc:  # pragma: no cover - runtime failures expected
                logger.error("Recovery attempt for %s failed: %s", node.id, retry_exc)
                return ExecutionResult(
                    node=node, success=False, error=str(retry_exc), attempted_recovery=True
                )

    def _store_outputs(self, node: TaskNode, output: Any, artifacts: Dict[str, Any]) -> None:
        if not node.produces:
            return
        for produced in node.produces:
            if isinstance(output, dict) and produced in output:
                artifacts[produced] = output[produced]
            else:
                artifacts[produced] = output

    def _update_neighbors(
        self,
        node_id: str,
        dependencies: Dict[str, Set[str]],
        indegree: Dict[str, int],
        ready: List[str],
    ) -> None:
        for dependent, deps in dependencies.items():
            if node_id in deps:
                indegree[dependent] -= 1
                if indegree[dependent] == 0 and dependent not in ready:
                    ready.append(dependent)

    def _record_memory(self, result: ExecutionResult) -> None:
        try:
            self.memory.store_text(
                result.output if result.success else result.error or "",
                namespace="execution",
                metadata={
                    "task": result.node.id,
                    "tool": result.node.tool,
                    "success": result.success,
                },
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Failed to persist execution result: %s", exc)

