"""Reflection utilities for summarizing execution traces."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from sentinel.agent_core.base import ExecutionTrace
from sentinel.logging.logger import get_logger
from sentinel.memory.memory_manager import MemoryManager
from sentinel.reflection.reflection_engine import ReflectionEngine

logger = get_logger(__name__)


def summarize_trace(trace: ExecutionTrace) -> str:
    timestamp = datetime.utcnow().isoformat()
    return f"[{timestamp}] {trace.summary()}"


class Reflector:
    """Adapter around the new :class:`ReflectionEngine` for backward compatibility."""

    def __init__(self, memory: MemoryManager, reflection_engine: ReflectionEngine) -> None:
        self.memory = memory
        self.engine = reflection_engine

    def reflect(self, trace: ExecutionTrace, reflection_type: str = "operational", goal: str | None = None) -> Dict[str, Any]:
        reflection = self.engine.reflect(trace, reflection_type=reflection_type, goal=goal)
        legacy_summary = summarize_trace(trace)
        try:
            namespace = f"reflection.{reflection_type}" if reflection_type else "reflection"
            self.memory.store_text(
                legacy_summary,
                namespace=namespace,
                metadata={"summary": True, "reflection_type": reflection_type},
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Failed to persist legacy reflection summary: %s", exc)
        logger.info("Reflection recorded for %s", reflection_type)
        return reflection
