"""Adaptive autonomy loop integrating HealthMonitor."""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from sentinel.agent_core.base import ExecutionResult, ExecutionTrace, Plan
from sentinel.agent_core.health import HealthMonitor
from sentinel.agent_core.planner import Planner
from sentinel.agent_core.reflection import Reflector
from sentinel.agent_core.worker import Worker
from sentinel.logging.logger import get_logger
from sentinel.memory.memory_manager import MemoryManager

log = get_logger(__name__)


class AutonomyLoop:
    """
    Adaptive multi-step autonomy loop.

    Responsibilities:
      - repeat planner → worker cycles
      - monitor health signals
      - apply adaptive recovery strategies
      - inject reflection when stuck
      - terminate cleanly when resolved
    """

    def __init__(
        self,
        planner: Planner,
        worker: Worker,
        reflector: Reflector,
        memory: MemoryManager,
        interval: float = 0.5,
        auto_start: bool = False,
    ) -> None:
        self.planner = planner
        self.worker = worker
        self.reflector = reflector
        self.memory = memory
        self.interval = interval
        self._running = auto_start

        # Integrate new health system
        self.health = HealthMonitor(self.planner.tool_registry)

    # ------------------------------------------------------------------

    def start(self) -> None:
        log.info("AutonomyLoop: starting.")
        self._running = True

    def stop(self) -> None:
        log.info("AutonomyLoop: stopping.")
        self._running = False

    # ------------------------------------------------------------------

    def run(self, goal: str, max_time: Optional[float] = None) -> ExecutionTrace:
        """
        Main loop.
        Continues until:
          - user stops
          - task ends normally
          - recovery fails
        """

        start_time = time.time()
        trace = ExecutionTrace()
        self._running = True

        self.memory.store_text(goal, namespace="goals", metadata={"type": "user_goal"})
        plan: Plan = self.planner.plan(goal)

        while self._running and plan.steps:
            for step in list(plan.steps):
                if not self._running:
                    break

                if max_time is not None and (time.time() - start_time) >= max_time:
                    log.info("AutonomyLoop: max time reached; terminating loop.")
                    self.stop()
                    break

                log.info("AutonomyLoop: executing step %s", step.step_id)
                step_started = time.time()
                result = self.worker._execute_step(step)  # noqa: SLF001
                duration = time.time() - step_started

                eval_input = self._build_eval_input(step, result)
                health = self.health.evaluate_step(eval_input, duration)
                self._log_health(health, duration)

                self._record_result(trace, result)

                if self.health.needs_recovery(health):
                    action = self.health.recovery_strategy(health)
                    log.warning("AutonomyLoop: recovery action required: %s", action)
                    recovered, replacement, new_plan = self._apply_recovery(
                        action, goal, step, trace
                    )

                    if replacement:
                        result = replacement

                    if new_plan:
                        plan = new_plan
                        log.info("AutonomyLoop: new plan generated with %d step(s).", len(plan.steps))
                        break

                    if not recovered:
                        log.error("AutonomyLoop: recovery failed; terminating task.")
                        self.stop()
                        break

                if health["score"] < 50 and self._running:
                    self._inject_reflection(trace, context="low_score")

                if not result.success:
                    log.info("AutonomyLoop: stopping after failed step %s.", step.step_id)
                    self.stop()
                    break

                time.sleep(self.interval)

            else:
                # Completed plan without breaks
                self.stop()
                break

        return trace

    # ------------------------------------------------------------------

    def _apply_recovery(
        self,
        action: str,
        goal: str,
        step: Any,
        trace: ExecutionTrace,
    ) -> tuple[bool, Optional[ExecutionResult], Optional[Plan]]:
        """
        Execute adaptive recovery behavior.
        Returns tuple(success, replacement_result, new_plan)
        """

        if action == "continue":
            return True, None, None

        if action == "retry_with_backoff":
            log.info("AutonomyLoop: retrying step %s with backoff...", step.step_id)
            time.sleep(self.interval * 2)
            retry_started = time.time()
            retry_result = self.worker._execute_step(step)  # noqa: SLF001
            retry_duration = time.time() - retry_started
            self._record_result(trace, retry_result)
            retry_health = self.health.evaluate_step(
                self._build_eval_input(step, retry_result), retry_duration
            )
            self._log_health(retry_health, retry_duration)
            return retry_result.success, retry_result, None

        if action == "replan":
            log.info("AutonomyLoop: replanning after step %s.", step.step_id)
            new_plan = self.planner.plan(goal)
            return bool(new_plan.steps), None, new_plan

        if action == "inject_reflection":
            log.info("AutonomyLoop: injecting reflection for recovery.")
            self._inject_reflection(trace, context="recovery")
            return True, None, None

        return False, None, None

    # ------------------------------------------------------------------

    def _inject_reflection(self, trace: ExecutionTrace, context: str) -> None:
        summary = self.reflector.reflect(trace)
        self.health.performance.record_reflection_improvement()
        self.memory.store_text(
            summary,
            namespace="reflection",
            metadata={"context": context, "autonomy": True},
        )

    def _record_result(self, trace: ExecutionTrace, result: ExecutionResult) -> None:
        trace.add(result)
        try:
            self.memory.store_text(
                result.output if result.success else result.error or "",
                namespace="execution",
                metadata={
                    "step_id": result.step.step_id,
                    "success": result.success,
                    "tool": result.step.tool_name,
                },
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            log.warning("AutonomyLoop: failed to record execution step: %s", exc)

    def _build_eval_input(self, step: Any, result: ExecutionResult) -> Dict[str, Any]:
        return {
            "step_id": getattr(step, "step_id", None),
            "description": getattr(step, "description", ""),
            "tool": getattr(step, "tool_name", None),
            "params": getattr(step, "params", {}),
            "error": result.error,
            "success": result.success,
        }

    def _log_health(self, health: Dict[str, Any], duration: float) -> None:
        log.debug("AutonomyLoop: health evaluation %s", health)
        log.info(
            "AutonomyLoop: step health -> score=%.2f duration=%.2fs hallu=%s repeat=%s slow=%s",
            health.get("score", 0),
            duration,
            bool(health.get("hallucinations")),
            bool(health.get("repeated_action")),
            bool(health.get("slow_step")),
        )

    # ------------------------------------------------------------------

    def export_state(self) -> Dict[str, Any]:
        """Expose autonomy + health state for debugging or API."""
        return {
            "running": self._running,
            "health": self.health.export_state(),
        }
