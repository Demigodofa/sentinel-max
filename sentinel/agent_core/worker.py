"""Worker responsible for executing task graphs."""
from __future__ import annotations

from typing import Optional

from sentinel.agent_core.base import ExecutionResult, ExecutionTrace
from sentinel.agent_core.sandbox import Sandbox
from sentinel.logging.logger import get_logger
from sentinel.memory.memory_manager import MemoryManager
from sentinel.planning.task_graph import TaskGraph, TopologicalExecutor
from sentinel.policy.policy_engine import PolicyEngine
from sentinel.tools.registry import ToolRegistry

logger = get_logger(__name__)


class Worker:
    def __init__(
        self,
        tool_registry: ToolRegistry,
        sandbox: Sandbox,
        memory: Optional[MemoryManager] = None,
        policy_engine: PolicyEngine | None = None,
        simulation_sandbox=None,
        world_model=None,
        approval_gate=None,
    ) -> None:
        self.tool_registry = tool_registry
        self.sandbox = sandbox
        self.memory = memory
        self.policy_engine = policy_engine
        self.executor = TopologicalExecutor(
            tool_registry,
            sandbox,
            memory=memory,
            policy_engine=policy_engine,
            simulation_sandbox=simulation_sandbox,
            world_model=world_model,
        )
        self.simulation_sandbox = simulation_sandbox
        self.world_model = world_model
        self.approval_gate = approval_gate

    def run(self, graph: TaskGraph) -> ExecutionTrace:
        logger.info("Worker executing task graph with %d nodes", len(graph.nodes))
        return self.executor.execute(graph)

    # ------------------------------------------------------------------
    def execute_node_real(self, node, context):
        """Execute a single node with real tool calls gated by policy and approval."""

        args = context.get("args", {}) if context else {}
        if self.policy_engine:
            if node.tool:
                self.policy_engine.check_execution_allowed(node.tool)
            runtime_context = {
                "start_time": context.get("start_time") if context else None,
                "cycles": context.get("cycles", 0) if context else 0,
                "consecutive_failures": context.get("consecutive_failures", 0)
                if context
                else 0,
                "elapsed": context.get("elapsed") if context else None,
            }
            self.policy_engine.check_runtime_limits(runtime_context)
        if self.approval_gate and not self.approval_gate.is_approved():
            raise PermissionError("Execution blocked: approval not granted")

        try:
            if node.tool is None:
                output = args or node.description
            else:
                output = self.sandbox.execute(self.tool_registry.call, node.tool, **args)
            result = ExecutionResult(node=node, success=True, output=output)
        except Exception as exc:  # pragma: no cover - runtime failures expected
            logger.error("Real execution failed for %s: %s", node.id, exc)
            result = ExecutionResult(node=node, success=False, error=str(exc))

        if self.memory:
            metadata = {
                "task": node.id,
                "tool": node.tool,
                "success": result.success,
                "error": result.error,
                "output": result.output,
                "type": "real_execution",
            }
            try:
                self.memory.store_fact("execution_real", key=node.id, value=metadata)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.warning("Failed to persist real execution metadata: %s", exc)
        return result
