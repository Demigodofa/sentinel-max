"""Task planner for Sentinel MAX."""
from __future__ import annotations

from typing import List

from sentinel.agent_core.base import Plan, PlanStep
from sentinel.tools.registry import ToolRegistry
from sentinel.logging.logger import get_logger

logger = get_logger(__name__)


class Planner:
    """Deterministic planner that converts goals into plan steps."""

    def __init__(self, tool_registry: ToolRegistry) -> None:
        self.tool_registry = tool_registry

    def plan(self, goal: str) -> Plan:
        """Generate a deterministic plan for the provided goal."""
        steps: List[PlanStep] = []
        normalized = goal.strip().lower()

        if normalized.startswith("search") or self.tool_registry.has_tool("web_search"):
            steps.append(
                PlanStep(
                    step_id=1,
                    description="Search for information",
                    tool_name="web_search" if self.tool_registry.has_tool("web_search") else None,
                    params={"query": goal},
                    expected_output="Relevant search results",
                )
            )
        else:
            steps.append(
                PlanStep(
                    step_id=1,
                    description="Echo the goal back",
                    tool_name=None,
                    params={"message": goal},
                    expected_output="Echoed response",
                )
            )

        logger.info("Generated plan with %d step(s) for goal: %s", len(steps), goal)
        return Plan(steps=steps)
