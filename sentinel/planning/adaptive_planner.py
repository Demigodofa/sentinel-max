"""Adaptive planner that grounds plans in memory, tools, and policies."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from sentinel.config.sandbox_config import get_sandbox_root
from sentinel.logging.logger import get_logger
from sentinel.memory.intelligence import MemoryContextBuilder
from sentinel.memory.memory_manager import MemoryManager
from sentinel.planning.task_graph import GraphValidator, TaskGraph, TaskNode
from sentinel.policy.policy_engine import PolicyEngine
from sentinel.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from sentinel.world.model import WorldModel

logger = get_logger(__name__)


@dataclass
class PlanContext:
    goal: str
    goal_type: str
    domain: str
    domain_capabilities: List[str]
    resources: List[str]
    memories: List[Dict[str, Any]]
    context_block: str
    tool_gaps: List[Dict[str, Any]]


class AdaptivePlanner:
    """TaskGraph-aware planner with memory grounding and policy alignment."""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        memory: MemoryManager,
        policy_engine: PolicyEngine,
        memory_context_builder: Optional[MemoryContextBuilder] = None,
        world_model: Optional["WorldModel"] = None,
        simulation_sandbox=None,
    ) -> None:
        self.tool_registry = tool_registry
        self.memory = memory
        self.policy_engine = policy_engine
        self.validator = GraphValidator(tool_registry)
        self.memory_context_builder = memory_context_builder or MemoryContextBuilder(
            memory, tool_registry=tool_registry
        )
        self.world_model = world_model
        self.simulation_sandbox = simulation_sandbox

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def plan(self, goal: str, reflection: Optional[Dict[str, Any]] = None) -> TaskGraph:
        try:
            plan_context = self._analyze_goal(goal)
            subgoals = self._generate_subgoals(plan_context, reflection)
            graph = self._build_graph(plan_context, subgoals, reflection)
            self._score_with_simulation(graph)
            self.policy_engine.evaluate_plan(graph, self.tool_registry)
            self.validator.validate(graph)
            self._record_plan(goal, graph, plan_context, reflection)
            return graph
        except Exception as exc:
            logger.warning("Adaptive planning failed, using deterministic fallback: %s", exc)
            plan_context = self._ensure_context(goal)
            fallback = self._deterministic_plan(goal)
            self._score_with_simulation(fallback)
            self.policy_engine.evaluate_plan(fallback, self.tool_registry)
            self.validator.validate(fallback)
            self._record_plan(goal, fallback, plan_context)
            return fallback

    def replan(self, goal: str, reflection: Dict[str, Any]) -> TaskGraph:
        return self.plan(goal, reflection=reflection)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _analyze_goal(self, goal: str) -> PlanContext:
        normalized = goal.lower()
        domain_name = ""
        domain_capabilities: List[str] = []
        resources: List[str] = []
        if self.world_model:
            domain_profile = self.world_model.get_domain(goal)
            domain_name = domain_profile.name
            domain_capabilities = self.world_model.list_capabilities(domain_profile.name)
            resources = [descriptor.name for descriptor in self.world_model.predict_required_resources(goal)]
        goal_type = self._goal_type_from(domain_name, normalized)
        memories, context_block = self.memory_context_builder.build_context(
            goal,
            goal_type,
            limit=6,
            include_tool_summary=True,
            tool_registry=self.tool_registry,
        )
        return PlanContext(
            goal=goal,
            goal_type=goal_type,
            domain=domain_name or goal_type,
            domain_capabilities=domain_capabilities,
            resources=resources,
            memories=memories,
            context_block=context_block,
            tool_gaps=[],
        )

    def _goal_type_from(self, domain_name: str, normalized_goal: str) -> str:
        domain_mapping = {
            "coding": "code_generation",
            "multi-service": "microservice",
            "pipelines": "pipeline_design",
            "devops": "devops",
            "web tasks": "web_task",
            "research": "research",
            "optimization": "optimization",
            "automation": "automation",
        }
        if domain_name in domain_mapping:
            return domain_mapping[domain_name]
        if any(keyword in normalized_goal for keyword in ["code", "bug", "refactor"]):
            return "code_generation"
        if any(keyword in normalized_goal for keyword in ["service", "api", "microservice"]):
            return "microservice"
        if any(keyword in normalized_goal for keyword in ["file", "process", "csv", "json"]):
            return "file_processing"
        return "info_query"

    def _ensure_context(self, goal: str) -> PlanContext:
        goal_type = self._goal_type_from("", goal.lower())
        memories, context_block = self.memory_context_builder.build_context(goal, goal_type, limit=6)
        return PlanContext(
            goal=goal,
            goal_type=goal_type or "fallback",
            domain=goal_type or "fallback",
            domain_capabilities=[],
            resources=[],
            memories=memories,
            context_block=context_block,
            tool_gaps=[],
        )

    def _generate_subgoals(self, plan_context: PlanContext, reflection: Optional[Dict[str, Any]]) -> List[str]:
        subgoals: List[str] = []
        if plan_context.goal_type == "code_generation":
            subgoals.extend(["analyze_requirements", "generate_code", "validate_code"])
        elif plan_context.goal_type == "microservice":
            subgoals.extend(["design_service", "generate_service", "validate_service"])
        elif plan_context.goal_type == "file_processing":
            subgoals.extend(["gather_files", "process_files", "summarize_outputs"])
        elif plan_context.goal_type == "pipeline_design":
            subgoals.extend(["define_sources", "design_pipeline", "validate_pipeline"])
        elif plan_context.goal_type == "devops":
            subgoals.extend(["assess_environment", "configure_deployment", "validate_rollout"])
        elif plan_context.goal_type == "web_task":
            subgoals.extend(["plan_navigation", "collect_web_data", "summarize_web_findings"])
        elif plan_context.goal_type == "research":
            subgoals.extend(["collect_sources", "synthesize_findings", "summarize_research"])
        elif plan_context.goal_type == "optimization":
            subgoals.extend(["profile_system", "apply_optimizations", "validate_performance"])
        elif plan_context.goal_type == "automation":
            subgoals.extend(["map_workflow", "compose_automation", "validate_automation"])
        else:
            subgoals.extend(["collect_information", "synthesize_answer"])
        if reflection:
            issues = reflection.get("issues_detected") or []
            if issues:
                subgoals.append("address_reflection_findings")
                for issue in issues:
                    subgoals.append(f"resolve_{issue}")
            plan_adjustment = reflection.get("plan_adjustment") or {}
            if plan_adjustment.get("action") == "replan":
                subgoals.append("apply_reflection_replan")
            for focus in plan_adjustment.get("focus", []):
                subgoals.append(f"focus_on_{focus}")
        return subgoals

    def _build_graph(
        self, plan_context: PlanContext, subgoals: List[str], reflection: Optional[Dict[str, Any]] = None
    ) -> TaskGraph:
        nodes: List[TaskNode] = []
        produces: Dict[str, str] = {}
        tool_gaps: List[Dict[str, Any]] = []
        for idx, subgoal in enumerate(subgoals, start=1):
            node_id = f"task_{idx}_{subgoal}"
            description = f"{subgoal.replace('_', ' ').title()} for goal"
            tool_name, args, output = self._select_tool(subgoal, plan_context.goal)
            if tool_name is None:
                gap_details = self._record_tool_gap(plan_context.goal, subgoal)
                if gap_details:
                    tool_gaps.append(gap_details)
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
        plan_context.tool_gaps = tool_gaps
        metadata = {
            "origin_goal": plan_context.goal,
            "domain": plan_context.domain,
            "domain_capabilities": plan_context.domain_capabilities,
            "resources": plan_context.resources,
            "knowledge_sources": [m.get("namespace", "") for m in plan_context.memories],
            "tool_choices": [node.tool for node in nodes],
            "reasoning_trace": self._reasoning_trace(plan_context, nodes),
            "semantic_tool_profile": self._semantic_profile(),
            "tool_gaps": tool_gaps,
        }
        if reflection:
            metadata.update(
                {
                    "reflection_issues": reflection.get("issues_detected", []),
                    "plan_adjustment": reflection.get("plan_adjustment", {}),
                }
            )
        graph = TaskGraph(nodes, metadata=metadata)
        return graph

    def _record_tool_gap(self, goal: str, subgoal: str) -> Dict[str, Any]:
        gap_details = {
            "type": "tool_gap",
            "goal": goal,
            "subgoal": subgoal,
            "requested_tool": subgoal.replace("_", " "),
            "reason": "No registered tool matched subgoal",
        }
        try:
            self.memory.store_fact(
                "policy_events",
                key=None,
                value=gap_details,
                metadata={"goal": goal, "event": "tool_gap"},
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to store tool gap policy event: %s", exc)
        return gap_details

    def _score_with_simulation(self, graph: TaskGraph) -> None:
        if not self.simulation_sandbox:
            return
        simulations = self.simulation_sandbox.simulate_taskgraph(graph, self.world_model)
        side_effects: Dict[str, List[str]] = {}
        warning_map: Dict[str, List[str]] = {}
        for node_id, result in simulations.items():
            if result.predicted_vfs_changes:
                side_effects[node_id] = list(result.predicted_vfs_changes.keys())
                graph.get(node_id).parallelizable = False
            if result.warnings:
                warning_map[node_id] = result.warnings
            if not result.success:
                raise ValueError(
                    f"Simulation failed for {node_id}: {', '.join(result.warnings) or 'unknown warning'}"
                )

        graph.add_metadata(
            simulation_predictions={
                node_id: {
                    "predicted_outputs": result.predicted_outputs,
                    "predicted_vfs_changes": result.predicted_vfs_changes,
                    "benchmark": result.benchmark,
                    "warnings": result.warnings,
                    "success": result.success,
                }
                for node_id, result in simulations.items()
            },
            simulation_side_effects=side_effects,
            simulation_warnings=warning_map,
            plan_score=self._score_from_simulation(simulations),
            predicted_effects={
                node_id: {
                    "side_effects": result.predicted_vfs_changes,
                    "failure_likelihood": result.benchmark.get("failure_likelihood", 0.0),
                }
                for node_id, result in simulations.items()
            },
        )

    def _select_tool(self, subgoal: str, goal: str) -> Tuple[Optional[str], Dict[str, Any], Optional[str]]:
        if "analyze" in subgoal and self.tool_registry.has_tool("code_analyzer"):
            return self._prefer_tool("code_analyzer", {"code": goal}, "code_assessment")
        if "generate_service" in subgoal and self.tool_registry.has_tool("microservice_builder"):
            return self._prefer_tool("microservice_builder", {"description": goal, "auto_start": False}, "service_spec")
        if "collect_information" in subgoal and self.tool_registry.has_tool("web_search"):
            return self._prefer_tool("web_search", {"query": goal}, "search_results")
        if "process_files" in subgoal and self.tool_registry.has_tool("internet_extract"):
            return self._prefer_tool("internet_extract", {"url": goal.split(" ")[-1]}, "extracted_content")
        if self.tool_registry.has_tool("internet_extract") and "synthesize" in subgoal:
            return self._prefer_tool("internet_extract", {"url": goal}, "synthesis")
        return None, {"message": goal}, None

    def _prefer_tool(
        self, tool_name: str, args: Dict[str, Any], output: Optional[str]
    ) -> Tuple[Optional[str], Dict[str, Any], Optional[str]]:
        profile = self._semantic_profile().get(tool_name, {})
        failure = profile.get("failure_likelihood", 0.0)
        if failure and failure > 0.8:
            return None, args, output
        return tool_name, args, output

    def _parallelizable_for(self, tool_name: Optional[str]) -> bool:
        if tool_name is None:
            return True
        schema = self.tool_registry.get_schema(tool_name)
        return bool(schema and schema.deterministic)

    def _semantic_profile(self) -> Dict[str, Any]:
        if not self.simulation_sandbox or not hasattr(self.simulation_sandbox, "predictor"):
            return {}
        return getattr(self.simulation_sandbox.predictor, "semantic_profiles", {})

    def _reasoning_trace(self, plan_context: PlanContext, nodes: List[TaskNode]) -> str:
        tool_descriptions = [f"{node.id}:{node.tool or 'no-tool'}" for node in nodes]
        return (
            f"Goal type={plan_context.goal_type}; domain={plan_context.domain or 'n/a'}; "
            f"resources={','.join(plan_context.resources)}; used memories={len(plan_context.memories)}; "
            f"tools={';'.join(tool_descriptions)}"
        )

    def _score_from_simulation(self, simulations: Dict[str, Any]) -> float:
        if not simulations:
            return 0.0
        total = len(simulations)
        warnings = sum(1 for result in simulations.values() if result.warnings)
        successes = sum(1 for result in simulations.values() if result.success)
        return round((successes - 0.5 * warnings) / total, 2)

    def _record_plan(
        self, goal: str, graph: TaskGraph, context: PlanContext, reflection: Optional[Dict[str, Any]] = None
    ) -> None:
        try:
            # GUI/CLI-friendly plan steps.
            # NOTE: Keep this aligned with sentinel.agent_core.base.PlanStep so the GUI can render it
            # without needing fragile key-mapping.
            steps = []
            for idx, node in enumerate(graph, start=1):
                description = (
                    getattr(node, "title", "")
                    or getattr(node, "action", "")
                    or getattr(node, "description", "")
                    or getattr(node, "tool", "")
                    or getattr(node, "id", "")
                )
                steps.append(
                    {
                        "step_id": idx,
                        "description": description,
                        "tool_name": getattr(node, "tool", None),
                        "params": getattr(node, "args", {}) or {},
                        # Keep original node ids in metadata so we can correlate execution results.
                        "metadata": {"node_id": getattr(node, "id", "")},
                        # For readability (and backwards-compat), keep dependency node ids here.
                        "depends_on": list(getattr(node, "requires", []) or []),
                    }
                )
            version = self._next_plan_version(goal)
            graph.add_metadata(plan_version=version)
            payload = {
                "goal": goal,
                "goal_type": context.goal_type,
                "metadata": graph.metadata,
                "nodes": [node.__dict__ for node in graph],
                "steps": steps,
                "version": version,
                "reflection": reflection or {},
            }
            self._persist_plan(goal, payload, metadata={"goal_type": context.goal_type, "version": version})
            planning_metadata = {"type": "planning_trace", "goal": goal, "goal_type": context.goal_type, "version": version}
            self.memory.store_text(
                graph.metadata.get("reasoning_trace", ""),
                namespace="planning_traces",
                metadata=planning_metadata,
            )
            self.memory.store_fact(
                "planning_traces",
                key=None,
                value={"goal": goal, "trace": graph.metadata.get("reasoning_trace", ""), "version": version},
                metadata=planning_metadata,
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Failed to record adaptive plan: %s", exc)

    def _persist_plan(self, goal: str, payload: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None) -> None:
        metadata = metadata or {}
        base_key = self._goal_key(goal)
        version = payload.get("version") or metadata.get("version")
        versioned_key = f"{base_key}.v{version}" if version else None
        record_metadata = {**metadata, "current": False}
        if versioned_key:
            self.memory.store_fact("plans", key=versioned_key, value=payload, metadata=record_metadata)
        record_metadata["current"] = True
        self.memory.store_fact("plans", key=base_key, value=payload, metadata=record_metadata)

    def _next_plan_version(self, goal: str) -> int:
        try:
            existing = self.memory.query("plans")
        except Exception:  # pragma: no cover - defensive fallback
            existing = []
        versions: List[int] = []
        for entry in existing:
            value = entry.get("value", {}) if isinstance(entry, dict) else {}
            if isinstance(value, dict) and value.get("goal") == goal:
                version = value.get("version") or entry.get("metadata", {}).get("version")
                if isinstance(version, int):
                    versions.append(version)
        return max(versions) + 1 if versions else 1

    def _goal_key(self, goal: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", goal).strip("_").lower()
        return slug or "plan"

    def record_plan_snapshot(self, goal: str, steps: List[Dict[str, Any]], metadata: Optional[Dict[str, Any]] = None) -> None:
        version = self._next_plan_version(goal)
        payload = {"goal": goal, "steps": steps, "metadata": metadata or {}, "version": version}
        self._persist_plan(goal, payload, metadata={**(metadata or {}), "version": version})

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
