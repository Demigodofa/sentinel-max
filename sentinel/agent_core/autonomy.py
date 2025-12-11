"""Autonomy loop for Sentinel MAX."""
from __future__ import annotations

import time
from typing import Optional

from sentinel.agent_core.planner import Planner
from sentinel.agent_core.worker import Worker
from sentinel.agent_core.reflection import Reflector
from sentinel.agent_core.base import Plan, ExecutionTrace
from sentinel.memory.memory_manager import MemoryManager
from sentinel.logging.logger import get_logger

logger = get_logger(__name__)


class AutonomyLoop:
    def __init__(
        self,
        planner: Planner,
        worker: Worker,
        reflector: Reflector,
        memory: MemoryManager,
    ) -> None:
        self.planner = planner
        self.worker = worker
        self.reflector = reflector
        self.memory = memory
        self._running = False

    def run(self, goal: str, max_time: Optional[float] = None) -> ExecutionTrace:
        start = time.time()
        self._running = True
        plan: Plan = self.planner.plan(goal)
        trace = ExecutionTrace()

        while self._running:
            trace = self.worker.run(plan)
            self.reflector.reflect(trace)
            if max_time is not None and (time.time() - start) >= max_time:
                logger.info("Autonomy loop timed out")
                break
            # For simplicity single iteration unless explicitly kept alive
            break

        self._running = False
        return trace

    def stop(self) -> None:
        self._running = False

    def export_state(self):
        return {
            "memory": self.memory.export_state(),
            "running": self._running,
        }
