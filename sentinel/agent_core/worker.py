"""Worker responsible for executing task graphs."""
from __future__ import annotations

from typing import Optional

from sentinel.agent_core.base import ExecutionTrace
from sentinel.agent_core.sandbox import Sandbox
from sentinel.logging.logger import get_logger
from sentinel.memory.memory_manager import MemoryManager
from sentinel.planning.task_graph import TaskGraph, TopologicalExecutor
from sentinel.tools.registry import ToolRegistry

logger = get_logger(__name__)


class Worker:
    def __init__(
        self, tool_registry: ToolRegistry, sandbox: Sandbox, memory: Optional[MemoryManager] = None
    ) -> None:
        self.tool_registry = tool_registry
        self.sandbox = sandbox
        self.memory = memory
        self.executor = TopologicalExecutor(tool_registry, sandbox, memory=memory)

    def run(self, graph: TaskGraph) -> ExecutionTrace:
        logger.info("Worker executing task graph with %d nodes", len(graph.nodes))
        return self.executor.execute(graph)
