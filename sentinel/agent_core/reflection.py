"""Reflection utilities for summarizing execution traces."""
from __future__ import annotations

from datetime import datetime

from sentinel.agent_core.base import ExecutionTrace
from sentinel.memory.memory_manager import MemoryManager
from sentinel.logging.logger import get_logger

logger = get_logger(__name__)


def summarize_trace(trace: ExecutionTrace) -> str:
    timestamp = datetime.utcnow().isoformat()
    return f"[{timestamp}] {trace.summary()}"


class Reflector:
    def __init__(self, memory: MemoryManager) -> None:
        self.memory = memory

    def reflect(self, trace: ExecutionTrace) -> str:
        summary = summarize_trace(trace)
        self.memory.store_text(summary, namespace="reflection", metadata={"summary": True})
        logger.info("Reflection recorded")
        return summary
