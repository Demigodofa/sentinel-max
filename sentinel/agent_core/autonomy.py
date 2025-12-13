"""Adaptive multi-cycle autonomy loop."""
from __future__ import annotations

from typing import Any, Dict, Optional
import time

from sentinel.agent_core.base import ExecutionTrace
from sentinel.agent_core.worker import Worker
from sentinel.logging.logger import get_logger
from sentinel.memory.memory_manager import MemoryManager
from sentinel.planning.adaptive_planner import AdaptivePlanner
from sentinel.planning.task_graph import TaskGraph
from sentinel.agent_core.reflection import Reflector
from sentinel.execution.execution_controller import ExecutionController, ExecutionMode

log = get_logger(__name__)


class AutonomyLoop:
    """Reflection-driven autonomy loop with DAG execution."""

    def __init__(
        self,
        planner: AdaptivePlanner,
        worker: Worker,
        execution_controller: ExecutionController,
        reflector: Reflector,
        memory: MemoryManager,
        interval: float = 0.5,
        auto_start: bool = False,
        cycle_limit: int = 3,
        timeout: Optional[float] = None,
        max_failed_cycles: int = 2,
    ) -> None:
        self.planner = planner
        self.worker = worker
        self.execution_controller = execution_controller
        self.reflector = reflector
        self.memory = memory
        self.interval = interval
        self._running = auto_start
        self.cycle_limit = cycle_limit
        self.timeout = timeout
        self.max_failed_cycles = max_failed_cycles
        self.last_reflection: Dict[str, Any] | None = None

    # ------------------------------------------------------------
    # PROJECT-LEVEL AUTONOMY LOOP
    # ------------------------------------------------------------

    def run_project_cycle(self, project_engine, project_id: str) -> Dict[str, Any]:
        """
        Execute one long-horizon cycle:
        - load project
        - build/validate plan
        - run dependency-ordered execution
        - reflect + refine
        """

        cycle_start = time.time()

        result = project_engine.run_project_cycle(project_id)

        cycle_end = time.time()
        elapsed = cycle_end - cycle_start

        result["cycle_time_sec"] = elapsed
        return result

    def start(self) -> None:
        log.info("AutonomyLoop: starting.")
        self._running = True

    def stop(self) -> None:
        log.info("AutonomyLoop: stopping.")
        self._running = False

    def run(
        self, taskgraph, execution_mode: ExecutionMode, parameters: Dict[str, Any]
    ) -> ExecutionTrace:
        """Execute a taskgraph using the execution controller then reflect."""

        self._running = True
        loop_start = time.time()
        goal = taskgraph if isinstance(taskgraph, str) else None
        graph = None
        if isinstance(taskgraph, str):
            graph = self.planner.plan(taskgraph, reflection=self.last_reflection)
        else:
            graph = taskgraph
        if hasattr(graph, "metadata") and not goal:
            goal = graph.metadata.get("origin_goal") if isinstance(graph.metadata, dict) else None

        trace: ExecutionTrace | None = None
        cycles = 0
        failed_cycles = 0
        while self._running:
            cycle_start = time.time()
            trace = self.execution_controller.request_execution(graph, execution_mode, parameters or {})
            self.memory.store_text(
                trace.summary(),
                namespace="execution.real_trace",
                metadata={"mode": execution_mode.value, "goal": goal, "cycle": cycles},
            )
            reflection = self._record_reflection(trace, "operational", execution_mode.value, goal)
            if reflection:
                self.last_reflection = reflection
            replan_requested = self._should_replan(reflection, trace)
            self._record_cycle_metadata(
                goal=goal,
                cycle=cycles,
                duration=time.time() - cycle_start,
                trace=trace,
                reflection=reflection,
                graph=graph,
                replan_requested=replan_requested,
            )
            if not replan_requested:
                break
            failed_cycles += 1 if trace.failed_nodes else 0
            cycles += 1
            if self.timeout and (time.time() - loop_start) >= self.timeout:
                break
            if self.max_failed_cycles and failed_cycles >= self.max_failed_cycles:
                break
            if self.cycle_limit and cycles >= self.cycle_limit:
                break
            if not goal:
                break
            graph = self.planner.replan(goal, reflection or {})
        self.stop()
        return trace or ExecutionTrace()

    def run_graph(
        self,
        graph: TaskGraph,
        goal: str,
        exit_conditions: Optional[Dict[str, Any]] = None,
    ) -> ExecutionTrace:
        """Execute a pre-built task graph and record reflections."""

        exit_conditions = exit_conditions or {}
        trace = ExecutionTrace()
        self._running = True
        self.memory.store_text(goal, namespace="goals", metadata={"type": "normalized"})
        cycle_trace = self.worker.run(graph)
        self._merge_trace(trace, cycle_trace)
        self._record_reflection(cycle_trace, "operational", "graph-execution", goal)
        if not cycle_trace.failed_nodes and self._goal_completed(exit_conditions, cycle_trace):
            self._record_reflection(cycle_trace, "user-preference", "graph-complete", goal)
        else:
            self._record_reflection(cycle_trace, "self-model", "graph-followup", goal)
        self.stop()
        return trace

    # ------------------------------------------------------------------
    def _goal_completed(self, exit_conditions: Dict[str, Any], trace: ExecutionTrace) -> bool:
        if exit_conditions.get("goal_complete") is True:
            return True
        if exit_conditions.get("require_success") and trace.failed_nodes:
            return False
        return not trace.failed_nodes

    def _merge_trace(self, main: ExecutionTrace, addition: ExecutionTrace) -> None:
        main.results.extend(addition.results)
        main.batches.extend(addition.batches)

    def _record_reflection(
        self, trace: ExecutionTrace, reflection_type: str, context: str, goal: str | None
    ) -> Dict[str, Any] | None:
        try:
            reflection = self.reflector.reflect(trace, reflection_type=reflection_type, goal=goal)
            self.memory.store_text(
                str(reflection),
                namespace=f"reflection.{reflection_type}",
                metadata={"context": context, "goal": goal},
            )
            self.last_reflection = reflection
            return reflection
        except Exception as exc:  # pragma: no cover - defensive logging
            log.warning("AutonomyLoop: failed to record reflection: %s", exc)
            return None

    def _should_replan(self, reflection: Optional[Dict[str, Any]], trace: ExecutionTrace) -> bool:
        if not self._running:
            return False
        if reflection:
            plan_adjustment = reflection.get("plan_adjustment") or {}
            if plan_adjustment.get("action") == "replan":
                return True
        if trace.failed_nodes:
            return True
        return False

    def _update_goal(self, goal: str, trace: ExecutionTrace) -> str:
        errors = [res.error for res in trace.failed_nodes if res.error]
        if errors:
            return f"Retry after failure: {goal}. Issues: {'; '.join(errors[:2])}"
        return goal

    def _record_cycle_metadata(
        self,
        goal: str | None,
        cycle: int,
        duration: float,
        trace: ExecutionTrace,
        reflection: Dict[str, Any] | None,
        graph: TaskGraph | None,
        replan_requested: bool,
    ) -> None:
        try:
            failed_nodes = []
            for res in trace.failed_nodes:
                node = getattr(res, "node", None)
                failed_nodes.append(getattr(node, "id", None) or "unknown")

            payload = {
                "goal": goal,
                "cycle": cycle,
                "duration_sec": round(duration, 3),
                "failed_nodes": failed_nodes,
                "replan_requested": replan_requested,
                "plan_version": getattr(graph, "metadata", {}).get("plan_version") if graph else None,
                "reflection_issues": (reflection or {}).get("issues_detected", []),
                "plan_adjustment": (reflection or {}).get("plan_adjustment", {}),
            }
            self.memory.store_fact("autonomy.cycles", key=None, value=payload)
        except Exception as exc:  # pragma: no cover - defensive logging
            log.warning("AutonomyLoop: failed to record cycle metadata: %s", exc)

