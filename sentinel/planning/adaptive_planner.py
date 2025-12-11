"""Adaptive planner that grounds plans in memory, tools, and policies."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from sentinel.logging.logger import get_logger
from sentinel.memory.intelligence import MemoryContextBuilder
from sentinel.memory.memory_manager import MemoryManager
from sentinel.planning.task_graph import GraphValidator, TaskGraph, TaskNode
from sentinel.policy.policy_engine import PolicyEngine
from sentinel.tools.registry import ToolRegistry

logger = get_logger(__name__)


@dataclass
class PlanContext:
    goal: str
    goal_type: str
    memories: List[Dict[str, Any]]
    context_block: str


class AdaptivePlanner:
    """TaskGraph-aware planner with memory grounding and policy alignment."""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        memory: MemoryManager,
        policy_engine: PolicyEngine,
        memory_context_builder: Optional[MemoryContextBuilder] = None,
    ) -> None:
        self.tool_registry = tool_registry
        self.memory = memory
        self.policy_engine = policy_engine
        self.validator = GraphValidator(tool_registry)
        self.memory_context_builder = memory_context_builder or MemoryContextBuilder(memory)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def plan(self, goal: str, reflection: Optional[Dict[str, Any]] = None) -> TaskGraph:
        try:
            plan_context = self._analyze_goal(goal)
            subgoals = self._generate_subgoals(plan_context, reflection)
            graph = self._build_graph(plan_context, subgoals)
            self.policy_engine.evaluate_plan(graph, self.tool_registry)
            self.validator.validate(graph)
            self._record_plan(goal, graph, plan_context)
            return graph
        except Exception as exc:
            logger.warning("Adaptive planning failed, using deterministic fallback: %s", exc)
            fallback = self._deterministic_plan(goal)
            self.policy_engine.evaluate_plan(fallback, self.tool_registry)
            self.validator.validate(fallback)
            self._record_plan(goal, fallback, PlanContext(goal, "fallback", [], ""))
            return fallback

    def replan(self, goal: str, reflection: Dict[str, Any]) -> TaskGraph:
        return self.plan(goal, reflection=reflection)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _analyze_goal(self, goal: str) -> PlanContext:
        normalized = goal.lower()
        if any(keyword in normalized for keyword in ["code", "bug", "refactor"]):
            goal_type = "code_generation"
        elif any(keyword in normalized for keyword in ["service", "api", "microservice"]):
            goal_type = "microservice"
        elif any(keyword in normalized for keyword in ["file", "process", "csv", "json"]):
            goal_type = "file_processing"
        else:
            goal_type = "info_query"
        memories, context_block = self.memory_context_builder.build_context(goal, goal_type, limit=6)
        return PlanContext(goal=goal, goal_type=goal_type, memories=memories, context_block=context_block)

    def _generate_subgoals(self, plan_context: PlanContext, reflection: Optional[Dict[str, Any]]) -> List[str]:
        subgoals: List[str] = []
        if plan_context.goal_type == "code_generation":
            subgoals.extend(["analyze_requirements", "generate_code", "validate_code"])
        elif plan_context.goal_type == "microservice":
            subgoals.extend(["design_service", "generate_service", "validate_service"])
        elif plan_context.goal_type == "file_processing":
            subgoals.extend(["gather_files", "process_files", "summarize_outputs"])
        else:
            subgoals.extend(["collect_information", "synthesize_answer"])
        if reflection and reflection.get("issues_detected"):
            subgoals.append("address_reflection_findings")
        return subgoals

    def _build_graph(self, plan_context: PlanContext, subgoals: List[str]) -> TaskGraph:
        nodes: List[TaskNode] = []
        produces: Dict[str, str] = {}
        for idx, subgoal in enumerate(subgoals, start=1):
            node_id = f"task_{idx}_{subgoal}"
            description = f"{subgoal.replace('_', ' ').title()} for goal"
            tool_name, args, output = self._select_tool(subgoal, plan_context.goal)
            requires = list(produces.keys()) if idx > 1 else []
            produces_key = output or f"artifact_{idx}"
            produces[produces_key] = node_id
            nodes.append(
                TaskNode(
                    id=node_id,
                    description=description,
                    tool=tool_name,
                    args=args,
                    requires=requires,
                    produces=[produces_key],
                    parallelizable=self._parallelizable_for(tool_name),
                )
            )
        nodes.append(
            TaskNode(
                id="sanity_validate",
                description="Sanity validation checkpoint",
                tool=None,
                args={"context": plan_context.context_block},
                requires=[nodes[-1].produces[0]] if nodes else [],
                produces=["sanity_report"],
                parallelizable=False,
            )
        )
        metadata = {
            "origin_goal": plan_context.goal,
            "knowledge_sources": [m.get("namespace", "") for m in plan_context.memories],
            "tool_choices": [node.tool for node in nodes],
            "reasoning_trace": self._reasoning_trace(plan_context, nodes),
        }
        graph = TaskGraph(nodes, metadata=metadata)
        return graph

    def _select_tool(self, subgoal: str, goal: str) -> Tuple[Optional[str], Dict[str, Any], Optional[str]]:
        if "analyze" in subgoal and self.tool_registry.has_tool("code_analyzer"):
            return "code_analyzer", {"code": goal}, "code_assessment"
        if "generate_service" in subgoal and self.tool_registry.has_tool("microservice_builder"):
            return "microservice_builder", {"description": goal, "auto_start": False}, "service_spec"
        if "collect_information" in subgoal and self.tool_registry.has_tool("web_search"):
            return "web_search", {"query": goal}, "search_results"
        if "process_files" in subgoal and self.tool_registry.has_tool("internet_extract"):
            return "internet_extract", {"url": goal.split(" ")[-1]}, "extracted_content"
        if self.tool_registry.has_tool("internet_extract") and "synthesize" in subgoal:
            return "internet_extract", {"url": goal}, "synthesis"
        return None, {"message": goal}, None

    def _parallelizable_for(self, tool_name: Optional[str]) -> bool:
        if tool_name is None:
            return True
        schema = self.tool_registry.get_schema(tool_name)
        return bool(schema and schema.deterministic)

    def _reasoning_trace(self, plan_context: PlanContext, nodes: List[TaskNode]) -> str:
        tool_descriptions = [f"{node.id}:{node.tool or 'no-tool'}" for node in nodes]
        return (
            f"Goal type={plan_context.goal_type}; used memories={len(plan_context.memories)}; "
            f"tools={';'.join(tool_descriptions)}"
        )

    def _record_plan(self, goal: str, graph: TaskGraph, context: PlanContext) -> None:
        try:
            self.memory.store_fact(
                "plans",
                key=None,
                value={
                    "goal": goal,
                    "goal_type": context.goal_type,
                    "metadata": graph.metadata,
                    "nodes": [node.__dict__ for node in graph],
                },
            )
            self.memory.store_text(
                graph.metadata.get("reasoning_trace", ""),
                namespace="planning_traces",
                metadata={"goal": goal, "goal_type": context.goal_type},
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Failed to record adaptive plan: %s", exc)

    def _deterministic_plan(self, goal: str) -> TaskGraph:
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
        return TaskGraph(nodes)
