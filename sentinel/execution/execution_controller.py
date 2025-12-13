"""Controlled real execution coordinator."""
from __future__ import annotations

import json
import time
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

from sentinel.agent_core.base import ExecutionResult, ExecutionTrace
from sentinel.dialog_manager import DialogManager
from sentinel.execution.approval_gate import ApprovalGate
from sentinel.logging.logger import get_logger
from sentinel.memory.memory_manager import MemoryManager
from sentinel.planning.task_graph import GraphValidator, TaskGraph, TaskNode
from sentinel.policy.policy_engine import PolicyEngine
from sentinel.agent_core.worker import Worker

logger = get_logger(__name__)


class ExecutionMode(Enum):
    UNTIL_COMPLETE = "until_complete"
    FOR_TIME = "for_time"
    UNTIL_NODE = "until_node"
    FOR_CYCLES = "for_cycles"
    UNTIL_CONDITION = "until_condition"
    WITH_CHECKINS = "with_checkins"


class ExecutionController:
    """Coordinate real execution with approvals, limits, and reporting."""

    def __init__(
        self,
        worker: Worker,
        policy_engine: PolicyEngine,
        approval_gate: ApprovalGate,
        dialog_manager: DialogManager,
        memory: MemoryManager,
    ) -> None:
        self.worker = worker
        self.policy_engine = policy_engine
        self.approval_gate = approval_gate
        self.dialog_manager = dialog_manager
        self.memory = memory
        self.validator = GraphValidator(worker.tool_registry)

    # ------------------------------------------------------------------
    def request_execution(self, taskgraph: TaskGraph, mode: ExecutionMode, parameters: Dict[str, Any]):
        mode = ExecutionMode(mode)
        if mode is ExecutionMode.UNTIL_COMPLETE:
            return self.execute_until_complete(taskgraph)
        if mode is ExecutionMode.FOR_TIME:
            return self.execute_for_time(taskgraph, parameters.get("seconds", 0))
        if mode is ExecutionMode.UNTIL_NODE:
            return self.execute_until_node(taskgraph, parameters.get("target_node_id"))
        if mode is ExecutionMode.FOR_CYCLES:
            return self.execute_for_cycles(taskgraph, parameters.get("max_cycles", 0))
        if mode is ExecutionMode.UNTIL_CONDITION:
            return self.execute_until_condition(taskgraph, parameters.get("condition_fn"))
        if mode is ExecutionMode.WITH_CHECKINS:
            return self.execute_with_checkins(taskgraph, parameters.get("interval_seconds", 1))
        raise ValueError(f"Unsupported execution mode: {mode}")

    # ------------------------------------------------------------------
    def execute_until_complete(self, taskgraph: TaskGraph) -> ExecutionTrace:
        return self._execute_graph(taskgraph)

    def execute_for_time(self, taskgraph: TaskGraph, seconds: float) -> ExecutionTrace:
        deadline = time.time() + max(seconds, 0)
        return self._execute_graph(
            taskgraph,
            should_stop=lambda trace, elapsed, cycles, node, result: time.time() >= deadline,
        )

    def execute_until_node(self, taskgraph: TaskGraph, target_node_id: str) -> ExecutionTrace:
        if not target_node_id:
            raise ValueError("target_node_id is required")
        return self._execute_graph(
            taskgraph,
            should_stop=lambda trace, elapsed, cycles, node, result: bool(
                node and node.id == target_node_id
            ),
        )

    def execute_for_cycles(self, taskgraph: TaskGraph, max_cycles: int) -> ExecutionTrace:
        limit = max(0, max_cycles)
        return self._execute_graph(
            taskgraph,
            should_stop=lambda trace, elapsed, cycles, node, result: cycles >= limit,
        )

    def execute_until_condition(
        self, taskgraph: TaskGraph, condition_fn: Optional[Callable[[ExecutionTrace], bool]]
    ) -> ExecutionTrace:
        condition_fn = condition_fn or (lambda trace: False)
        return self._execute_graph(
            taskgraph,
            should_stop=lambda trace, elapsed, cycles, node, result: condition_fn(trace),
        )

    def execute_with_checkins(self, taskgraph: TaskGraph, interval_seconds: float) -> ExecutionTrace:
        interval_seconds = max(interval_seconds, 0.1)
        return self._execute_graph(taskgraph, checkin_interval=interval_seconds)

    # ------------------------------------------------------------------
    def _execute_graph(
        self,
        graph: TaskGraph,
        should_stop: Optional[
            Callable[[ExecutionTrace, float, int, Optional[TaskNode], Optional[ExecutionResult]], bool]
        ] = None,
        checkin_interval: Optional[float] = None,
    ) -> ExecutionTrace:
        self.validator.validate(graph)
        produced_by = self._build_produced_map(graph)
        dependencies = self._build_dependency_graph(graph, produced_by)
        indegree = {node_id: len(deps) for node_id, deps in dependencies.items()}
        ready: List[str] = [node_id for node_id, deg in indegree.items() if deg == 0]
        artifacts: Dict[str, Any] = {}
        executed: Set[str] = set()
        failed: Set[str] = set()
        trace = ExecutionTrace()
        start_time = time.time()
        last_checkin = start_time
        cycles = 0
        consecutive_failures = 0

        while ready:
            if should_stop and should_stop(trace, time.time() - start_time, cycles, None, None):
                break
            node_id = ready.pop(0)
            node = graph.get(node_id)

            if any(dep in failed for dep in dependencies[node_id]):
                result = ExecutionResult(node=node, success=False, error="Upstream failure")
                trace.add(result)
                failed.add(node.id)
                self._record_memory(result)
                self._update_neighbors(node_id, dependencies, indegree, ready)
                continue

            args = self._resolve_args(node, artifacts)
            try:
                self._ensure_simulation_passed(node)
                runtime_policy = self.policy_engine.check_runtime_limits(
                    {
                        "start_time": start_time,
                        "elapsed": time.time() - start_time,
                        "cycles": cycles,
                        "consecutive_failures": consecutive_failures,
                        "max_cycles": self.policy_engine.max_cycles,
                    },
                    enforce=False,
                )
                execution_policy = runtime_policy
                if node.tool:
                    execution_policy = runtime_policy.merge(
                        self.policy_engine.check_execution_allowed(node.tool, enforce=False)
                    )
                if not execution_policy.allowed:
                    result = ExecutionResult(
                        node=node,
                        success=False,
                        error="; ".join(execution_policy.reasons) or "Policy blocked",
                        policy=execution_policy,
                    )
                else:
                    self.approval_gate.request_approval(
                        f"Execute task {node.id}: {node.description}"
                    )
                    if not self.approval_gate.is_approved():
                        raise PermissionError("Approval required for real execution")
                    result = self.worker.execute_node_real(
                        node,
                        {
                            "args": args,
                            "artifacts": artifacts,
                            "start_time": start_time,
                            "cycles": cycles,
                            "consecutive_failures": consecutive_failures,
                            "elapsed": time.time() - start_time,
                        },
                    )
                if result.success:
                    executed.add(node.id)
                    consecutive_failures = 0
                    self._store_outputs(node, result.output, artifacts)
                else:
                    failed.add(node.id)
                    consecutive_failures += 1
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.warning("Execution halted for node %s: %s", node.id, exc)
                result = ExecutionResult(node=node, success=False, error=str(exc))
                failed.add(node.id)
                consecutive_failures += 1
            trace.add(result)
            self._record_memory(result)
            cycles += 1
            if checkin_interval and (time.time() - last_checkin) >= checkin_interval:
                self.dialog_manager.notify_execution_status(
                    {"node": node.id, "cycles": cycles, "elapsed": time.time() - start_time}
                )
                last_checkin = time.time()
            if should_stop and should_stop(trace, time.time() - start_time, cycles, node, result):
                break
            self._update_neighbors(node_id, dependencies, indegree, ready)

        if checkin_interval:
            self.dialog_manager.notify_execution_status(
                {"status": "completed", "elapsed": time.time() - start_time, "cycles": cycles}
            )
        self._persist_trace(trace, artifacts, executed, failed)
        return trace

    # ------------------------------------------------------------------
    def _ensure_simulation_passed(self, node: TaskNode) -> None:
        records = self.memory.query("simulations", key=node.id)
        if records:
            value = records[0].get("value", {})
            success = False
            if isinstance(value, dict):
                success = value.get("success", False)
            if not success:
                raise PermissionError(f"Simulation predicted failure for {node.id}")

    def _resolve_args(self, node: TaskNode, artifacts: Dict[str, Any]) -> Dict[str, Any]:
        args = dict(node.args)
        for requirement in node.requires:
            if requirement in artifacts and requirement not in args:
                args[requirement] = artifacts[requirement]
        return args

    def _build_produced_map(self, graph: TaskGraph) -> Dict[str, str]:
        produced: Dict[str, str] = {}
        for node in graph:
            for artifact in node.produces:
                produced[artifact] = node.id
        return produced

    def _build_dependency_graph(self, graph: TaskGraph, produced_by: Dict[str, str]) -> Dict[str, Set[str]]:
        deps: Dict[str, Set[str]] = {node.id: set() for node in graph}
        for node in graph:
            for requirement in node.requires:
                producer = produced_by.get(requirement)
                if producer:
                    deps[node.id].add(producer)
        return deps

    def _update_neighbors(self, node_id: str, dependencies: Dict[str, Set[str]], indegree: Dict[str, int], ready: List[str]):
        for dependent, deps in dependencies.items():
            if node_id in deps:
                indegree[dependent] -= 1
                if indegree[dependent] == 0 and dependent not in ready:
                    ready.append(dependent)

    def _store_outputs(self, node: TaskNode, output: Any, artifacts: Dict[str, Any]) -> None:
        if not node.produces:
            return
        for produced in node.produces:
            if isinstance(output, dict) and produced in output:
                artifacts[produced] = output[produced]
            else:
                artifacts[produced] = output

    def _record_memory(self, result: ExecutionResult) -> None:
        try:
            payload = {
                "task": result.node.id,
                "tool": result.node.tool,
                "success": result.success,
                "error": result.error,
                "output": result.output,
            }
            metadata = {"task": result.node.id, "tool": result.node.tool, "success": result.success, "type": "node_result"}
            self.memory.store_fact("execution", key=result.node.id, value=payload, metadata=metadata)
            self.memory.store_text(
                json.dumps(payload, ensure_ascii=False),
                namespace="execution",
                metadata=metadata,
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Failed to write execution log: %s", exc)
        self.dialog_manager.notify_execution_status(
            {"task": result.node.id, "success": result.success, "error": result.error}
        )

    def _persist_trace(
        self, trace: ExecutionTrace, artifacts: Dict[str, Any], executed: Set[str], failed: Set[str]
    ) -> None:
        try:
            summary_payload = {
                "type": "summary",
                "successes": len([res for res in trace.results if res.success]),
                "failures": len(trace.failed_nodes),
                "executed": list(executed),
                "failed": list(failed),
            }
            self.memory.store_text(
                trace.summary(),
                namespace="execution",
                metadata=summary_payload,
            )
            self.memory.store_fact("execution", key=None, value=summary_payload, metadata=summary_payload)
            if artifacts:
                artifact_payload = {
                    "type": "artifacts",
                    "artifacts": artifacts,
                    "executed": list(executed),
                    "failed": list(failed),
                }
                self.memory.store_fact(
                    "execution",
                    key=None,
                    value=artifact_payload,
                    metadata={"type": "artifacts", "executed": list(executed), "failed": list(failed)},
                )
                self.memory.store_text(
                    json.dumps(artifact_payload, ensure_ascii=False),
                    namespace="execution",
                    metadata={"type": "artifacts", "executed": list(executed), "failed": list(failed)},
                )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Failed to persist execution summary: %s", exc)
