"""Task planner for Sentinel MAX."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import List, Optional
from uuid import uuid4

from sentinel.logging.logger import get_logger
from sentinel.agent_core.base import PlanStep
from sentinel.memory.memory_manager import MemoryManager
from sentinel.planning.task_graph import GraphValidator, TaskGraph, TaskNode
from sentinel.tools.registry import ToolRegistry

logger = get_logger(__name__)


class Planner:
    """Deterministic planner that converts goals into DAG tasks."""

    def __init__(self, tool_registry: ToolRegistry, memory: Optional[MemoryManager] = None) -> None:
        self.tool_registry = tool_registry
        self.memory = memory
        self.validator = GraphValidator(tool_registry)

    def _parallelizable_for(self, tool_name: str | None) -> bool:
        if tool_name is None:
            return True
        schema = self.tool_registry.get_schema(tool_name)
        return bool(schema and schema.deterministic)

    def plan(self, goal: str) -> TaskGraph:
        """Generate a validated :class:`TaskGraph` for the provided goal."""

        normalized = goal.strip().lower()
        nodes: List[TaskNode] = []

        if "code" in normalized and self.tool_registry.has_tool("code_analyzer"):
            nodes.append(
                TaskNode(
                    id="analyze_code",
                    description="Analyze provided code for safety",
                    tool="code_analyzer",
                    args={"code": goal},
                    produces=["code_assessment"],
                    parallelizable=self._parallelizable_for("code_analyzer"),
                )
            )
        elif "service" in normalized and self.tool_registry.has_tool("microservice_builder"):
            nodes.append(
                TaskNode(
                    id="design_service",
                    description="Generate microservice from description",
                    tool="microservice_builder",
                    args={"description": goal, "auto_start": False},
                    produces=["service_spec"],
                    parallelizable=self._parallelizable_for("microservice_builder"),
                )
            )
        elif "scrape" in normalized or "extract" in normalized:
            if self.tool_registry.has_tool("web_search"):
                nodes.append(
                    TaskNode(
                        id="search",
                        description="Search for relevant sources",
                        tool="web_search",
                        args={"query": goal},
                        produces=["search_results"],
                        parallelizable=self._parallelizable_for("web_search"),
                    )
                )
            nodes.append(
                TaskNode(
                    id="extract",
                    description="Extract information from the web",
                    tool="internet_extract" if self.tool_registry.has_tool("internet_extract") else None,
                    args={"url": goal.split(" ")[-1]},
                    requires=["search_results"] if self.tool_registry.has_tool("web_search") else [],
                    produces=["extracted_content"],
                    parallelizable=self._parallelizable_for(
                        "internet_extract" if self.tool_registry.has_tool("internet_extract") else None
                    ),
                )
            )
        elif normalized.startswith("search") or self.tool_registry.has_tool("web_search"):
            nodes.append(
                TaskNode(
                    id="search",
                    description="Search for information",
                    tool="web_search" if self.tool_registry.has_tool("web_search") else None,
                    args={"query": goal},
                    produces=["search_results"],
                    parallelizable=self._parallelizable_for(
                        "web_search" if self.tool_registry.has_tool("web_search") else None
                    ),
                )
            )
        else:
            nodes.append(
                TaskNode(
                    id="echo",
                    description="Echo the goal back",
                    tool=None,
                    args={"message": goal},
                    produces=["echoed_message"],
                    parallelizable=self._parallelizable_for(None),
                )
            )

        graph = TaskGraph(nodes)
        self.validator.validate(graph)
        logger.info("Generated task graph with %d node(s) for goal: %s", len(nodes), goal)
        self._record_plan(goal, graph)
        return graph

    def _record_plan(self, goal: str, graph: TaskGraph) -> None:
        if not self.memory:
            return
        try:
            self.memory.store_fact(
                "plans",
                key=str(uuid4()),
                value={
                    "goal": goal,
                    "nodes": [node.__dict__ for node in graph],
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Failed to record plan in memory: %s", exc)


class SentinelPlanner:
    """
    Deterministic planner that transforms goals into multi-phase steps.
    Project-aware: includes project_id, goal_id, and phase tagging.
    """

    def __init__(self) -> None:
        pass

    # ------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------

    def plan(
        self,
        goal_text: str,
        *,
        project_id: str | None = None,
        goal_id: str | None = None,
        phase: int | None = None,
    ) -> List[PlanStep]:
        """
        Generates deterministic steps from goal text.
        Includes optional project metadata.
        """

        base_hash = hashlib.sha256(goal_text.encode()).hexdigest()[:8]

        raw_steps = self._expand_goal(goal_text)

        steps: List[PlanStep] = []
        for i, action in enumerate(raw_steps, start=1):
            step = PlanStep(
                step_id=i,
                description=action,
                depends_on=[],
                metadata={
                    "project_id": project_id,
                    "goal_id": goal_id,
                    "phase": phase,
                    "ordinal": i,
                    "goal_fingerprint": base_hash,
                },
            )
            steps.append(step)

        return steps

    # ------------------------------------------------------------
    # INTERNAL GOAL BREAKDOWN
    # ------------------------------------------------------------

    def _expand_goal(self, text: str) -> List[str]:
        """
        Convert a goal into deterministic substeps.
        No LLM calls. Fully deterministic.
        """

        text = text.strip()

        if len(text.split()) <= 4:
            return [
                f"Investigate goal: {text}",
                f"Define output requirements for: {text}",
                f"Produce actionable instructions for: {text}",
            ]

        # Larger goals
        return [
            f"Summarize intent of: {text}",
            f"Extract required knowledge for: {text}",
            f"Determine blocking dependencies for: {text}",
            f"Draft execution sequence for: {text}",
            f"Generate verification criteria for: {text}",
        ]
