"""Task planner for Sentinel MAX."""
from __future__ import annotations

from typing import List, Optional
from uuid import uuid4
from datetime import datetime

from sentinel.agent_core.base import Plan, PlanStep
from sentinel.memory.memory_manager import MemoryManager
from sentinel.tools.registry import ToolRegistry
from sentinel.logging.logger import get_logger

logger = get_logger(__name__)


class Planner:
    """Deterministic planner that converts goals into plan steps."""

    def __init__(self, tool_registry: ToolRegistry, memory: Optional[MemoryManager] = None) -> None:
        self.tool_registry = tool_registry
        self.memory = memory

    def plan(self, goal: str) -> Plan:
        """Generate a deterministic plan for the provided goal."""
        steps: List[PlanStep] = []
        normalized = goal.strip().lower()

        if "code" in normalized and self.tool_registry.has_tool("code_analyzer"):
            steps.append(
                PlanStep(
                    step_id=1,
                    description="Analyze provided code for safety",
                    tool_name="code_analyzer",
                    params={"code": goal},
                    expected_output="Risk assessment",
                )
            )
        elif "service" in normalized and self.tool_registry.has_tool("microservice_builder"):
            steps.append(
                PlanStep(
                    step_id=1,
                    description="Generate microservice from description",
                    tool_name="microservice_builder",
                    params={"description": goal},
                    expected_output="FastAPI microservice specification",
                )
            )
        elif "scrape" in normalized or "extract" in normalized:
            steps.append(
                PlanStep(
                    step_id=1,
                    description="Extract information from the web",
                    tool_name="internet_extract" if self.tool_registry.has_tool("internet_extract") else None,
                    params={"url": goal.split(" ")[-1]},
                    expected_output="Cleaned web content",
                )
            )
        elif normalized.startswith("search") or self.tool_registry.has_tool("web_search"):
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
        plan = Plan(steps=steps)
        if self.memory:
            try:
                self.memory.store_fact(
                    "plans",
                    key=str(uuid4()),
                    value={
                        "goal": goal,
                        "steps": [step.__dict__ for step in steps],
                        "created_at": datetime.utcnow().isoformat(),
                    },
                )
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.warning("Failed to record plan in memory: %s", exc)
        return plan
