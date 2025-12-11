"""Adaptive multi-cycle autonomy loop."""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from sentinel.agent_core.base import ExecutionTrace
from sentinel.agent_core.worker import Worker
from sentinel.logging.logger import get_logger
from sentinel.memory.memory_manager import MemoryManager
from sentinel.planning.adaptive_planner import AdaptivePlanner
from sentinel.agent_core.reflection import Reflector

log = get_logger(__name__)


class AutonomyLoop:
    """Reflection-driven autonomy loop with DAG execution."""

    def __init__(
        self,
        planner: AdaptivePlanner,
        worker: Worker,
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
        self.reflector = reflector
        self.memory = memory
        self.interval = interval
        self._running = auto_start
        self.cycle_limit = cycle_limit
        self.timeout = timeout
        self.max_failed_cycles = max_failed_cycles
        self.last_reflection: Dict[str, Any] | None = None

    def start(self) -> None:
        log.info("AutonomyLoop: starting.")
        self._running = True

    def stop(self) -> None:
        log.info("AutonomyLoop: stopping.")
        self._running = False

    def run(
        self,
        goal: str,
        cycle_limit: Optional[int] = None,
        timeout: Optional[float] = None,
        exit_conditions: Optional[Dict[str, Any]] = None,
    ) -> ExecutionTrace:
        """Run planner → worker → reflection cycles until exit conditions are met."""

        cycle_limit = cycle_limit or self.cycle_limit
        timeout = timeout if timeout is not None else self.timeout
        exit_conditions = exit_conditions or {}

        trace = ExecutionTrace()
        self._running = True
        current_goal = goal
        failed_cycles = 0
        start_time = time.time()
        self.memory.store_text(goal, namespace="goals", metadata={"type": "user_goal"})
        previous_signature = None

        for cycle in range(1, cycle_limit + 1):
            if not self._running:
                break
            if timeout is not None and (time.time() - start_time) >= timeout:
                log.info("AutonomyLoop: timeout reached; stopping.")
                break

            graph = self.planner.plan(current_goal, reflection=self.last_reflection)
            signature = graph.signature()
            if previous_signature == signature:
                failed_cycles += 1
                self._record_reflection(trace, "strategic", "Repeated plan detected", current_goal)
                if failed_cycles >= self.max_failed_cycles:
                    log.warning("AutonomyLoop: repeat-plan guard triggered.")
                    break
            previous_signature = signature

            cycle_trace = self.worker.run(graph)
            self._merge_trace(trace, cycle_trace)
            reflection = self._record_reflection(cycle_trace, "operational", f"cycle_{cycle}", current_goal)
            if reflection and reflection.get("plan_adjustment", {}).get("action") == "replan":
                current_goal = self._update_goal(current_goal, cycle_trace)
                previous_signature = None
                continue

            if not cycle_trace.failed_nodes and self._goal_completed(exit_conditions, cycle_trace):
                self._record_reflection(cycle_trace, "user-preference", "goal-complete", current_goal)
                self.stop()
                break

            if cycle_trace.failed_nodes:
                failed_cycles += 1
                self._record_reflection(cycle_trace, "self-model", "tool-failure", current_goal)
                if failed_cycles >= self.max_failed_cycles:
                    log.error("AutonomyLoop: too many failed cycles; stopping.")
                    break
                current_goal = self._update_goal(current_goal, cycle_trace)
                continue

            # Strategic reflection for continued progress
            self._record_reflection(trace, "strategic", f"cycle_{cycle}_progress", current_goal)
            time.sleep(self.interval)

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

    def _update_goal(self, goal: str, trace: ExecutionTrace) -> str:
        errors = [res.error for res in trace.failed_nodes if res.error]
        if errors:
            return f"Retry after failure: {goal}. Issues: {'; '.join(errors[:2])}"
        return goal

