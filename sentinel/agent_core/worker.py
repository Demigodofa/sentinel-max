"""Worker responsible for executing task graphs."""
from __future__ import annotations

from typing import Optional

from sentinel.agent_core.base import ExecutionTrace
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
    ) -> None:
        self.tool_registry = tool_registry
        self.sandbox = sandbox
        self.memory = memory
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

    def run(self, graph: TaskGraph) -> ExecutionTrace:
        logger.info("Worker executing task graph with %d nodes", len(graph.nodes))
        return self.executor.execute(graph)
