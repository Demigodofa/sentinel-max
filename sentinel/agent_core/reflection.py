"""Reflection utilities for summarizing execution traces."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List
import time

from sentinel.agent_core.base import ExecutionTrace
from sentinel.logging.logger import get_logger
from sentinel.memory.memory_manager import MemoryManager
from sentinel.reflection.reflection_engine import ReflectionEngine as CoreReflectionEngine

logger = get_logger(__name__)


class ProjectReflectionEngine:
    """
    Produces step-level and project-level reflections.
    Reflection output influences plan refinement.
    """

    def __init__(self) -> None:
        pass

    # ------------------------------------------------------------
    # PROJECT-LEVEL REFLECTION
    # ------------------------------------------------------------

    def reflect_project(
        self,
        project_data: Dict[str, Any],
        plan: Dict[str, Any],
        progress: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Analyze progress, detect blocking issues, identify refinement triggers.
        """

        pct = progress["pct"]
        cycles_exist = any(project_data.get("dependencies", {}).get("cycles", []))
        unresolved = project_data.get("dependencies", {}).get("unresolved", [])

        issues: List[str] = []

        # Low progress indicator
        if pct < 10 and len(plan) > 5:
            issues.append("Low early progress")

        # Cycles always require refinement
        if cycles_exist:
            issues.append("Dependency cycles detected")

        if unresolved:
            issues.append("Unresolved dependencies")

        requires_refinement = len(issues) > 0

        return {
            "timestamp": time.time(),
            "progress_pct": pct,
            "issues": issues,
            "requires_refinement": requires_refinement,
        }


# Backwards compatibility for imports expecting ReflectionEngine
class ReflectionEngine(ProjectReflectionEngine):
    """Alias to retain legacy import paths."""

    pass


def summarize_trace(trace: ExecutionTrace) -> str:
    timestamp = datetime.now(timezone.utc).isoformat()
    return f"[{timestamp}] {trace.summary()}"


class Reflector:
    """Adapter around the new :class:`ReflectionEngine` for backward compatibility."""

    def __init__(self, memory: MemoryManager, reflection_engine: CoreReflectionEngine) -> None:
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
