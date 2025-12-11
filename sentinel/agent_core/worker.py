"""Worker responsible for executing plan steps."""
from __future__ import annotations

from typing import Any, Optional

from sentinel.agent_core.base import Plan, ExecutionTrace, ExecutionResult, PlanStep
from sentinel.agent_core.sandbox import Sandbox
from sentinel.memory.memory_manager import MemoryManager
from sentinel.tools.registry import ToolRegistry
from sentinel.logging.logger import get_logger

logger = get_logger(__name__)


class Worker:
    def __init__(
        self, tool_registry: ToolRegistry, sandbox: Sandbox, memory: Optional[MemoryManager] = None
    ) -> None:
        self.tool_registry = tool_registry
        self.sandbox = sandbox
        self.memory = memory

    def run(self, plan: Plan) -> ExecutionTrace:
        trace = ExecutionTrace()
        for step in plan.steps:
            result = self._execute_step(step)
            trace.add(result)
            if self.memory:
                try:
                    self.memory.store_text(
                        result.output if result.success else result.error or "",
                        namespace="execution",
                        metadata={
                            "step_id": step.step_id,
                            "success": result.success,
                            "tool": step.tool_name,
                        },
                    )
                except Exception as exc:  # pragma: no cover - defensive logging
                    logger.warning("Failed to record execution step: %s", exc)
            if not result.success:
                break
        return trace

    def _execute_step(self, step: PlanStep) -> ExecutionResult:
        logger.info("Executing step %s", step.step_id)
        try:
            if step.tool_name:
                output: Any = self.sandbox.execute(
                    self.tool_registry.call, step.tool_name, **step.params
                )
            else:
                output = step.params.get("message", step.description)
            return ExecutionResult(step=step, success=True, output=output)
        except Exception as exc:  # pragma: no cover - execution errors expected
            logger.error("Step %s failed: %s", step.step_id, exc)
            return ExecutionResult(step=step, success=False, error=str(exc))
