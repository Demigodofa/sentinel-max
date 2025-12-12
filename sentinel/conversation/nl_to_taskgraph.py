"""Natural language to TaskGraph translation layer."""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple

from sentinel.logging.logger import get_logger
from sentinel.planning.task_graph import GraphValidator, TaskGraph, TaskNode
from sentinel.policy.policy_engine import PolicyEngine
from sentinel.tools.registry import ToolRegistry
from sentinel.world.model import WorldModel
from sentinel.conversation.intent_engine import NormalizedGoal

logger = get_logger(__name__)


class NLToTaskGraph:
    """Translate normalized conversational goals into validated TaskGraphs."""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        policy_engine: PolicyEngine,
        world_model: WorldModel,
        validator: Optional[GraphValidator] = None,
    ) -> None:
        self.tool_registry = tool_registry
        self.policy_engine = policy_engine
        self.world_model = world_model
        self.validator = validator or GraphValidator(tool_registry)

    def translate(self, normalized_goal: NormalizedGoal) -> TaskGraph:
        subgoals = self._derive_subgoals(normalized_goal)
        nodes = self._build_nodes(normalized_goal, subgoals)
        self._attach_validation(nodes, normalized_goal)
        metadata = self._build_metadata(normalized_goal, nodes, subgoals)
        graph = TaskGraph(nodes, metadata=metadata)
        available_inputs = set(normalized_goal.parameters.keys())
        self.validator.validate(graph, available_inputs=available_inputs)
        self.policy_engine.evaluate_plan(graph, self.tool_registry)
        return graph

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _derive_subgoals(self, normalized_goal: NormalizedGoal) -> List[Dict[str, object]]:
        domain = normalized_goal.domain
        goal_type = normalized_goal.type
        subgoals: List[Dict[str, object]] = []
        if goal_type == "web_scraping" or domain == "web_interaction" or normalized_goal.parameters.get("target_website"):
            subgoals.extend(
                [
                    {"name": "analyze_target", "action": "inspect target", "parallelizable": True},
                    {"name": "open_site", "action": "open target site", "parallelizable": False},
                    {"name": "collect_content", "action": "collect page content", "parallelizable": False},
                    {"name": "summarize_results", "action": "summarize", "parallelizable": True},
                ]
            )
            browser_actions: List[str] = normalized_goal.parameters.get("browser_actions", [])
            if "authenticate" in browser_actions:
                subgoals.insert(2, {"name": "authenticate", "action": "perform login", "parallelizable": False})
        elif goal_type == "build_microservice" or domain == "multi_service":
            subgoals.extend(
                [
                    {"name": "design_interface", "action": "design api", "parallelizable": True},
                    {"name": "generate_service", "action": "implement service", "parallelizable": False},
                    {"name": "connect_services", "action": "wire services", "parallelizable": False},
                ]
            )
        elif goal_type == "devops_pipeline" or domain == "devops":
            subgoals.extend(
                [
                    {"name": "assess_environment", "action": "inspect environment", "parallelizable": True},
                    {"name": "configure_pipeline", "action": "configure ci/cd", "parallelizable": False},
                    {"name": "validate_release", "action": "run smoke tests", "parallelizable": False},
                ]
            )
        elif goal_type == "schedule_planning" or domain == "real_world_planning":
            subgoals.extend(
                [
                    {"name": "gather_requirements", "action": "collect schedule inputs", "parallelizable": True},
                    {"name": "compose_plan", "action": "draft plan", "parallelizable": False},
                    {"name": "publish_plan", "action": "publish summary", "parallelizable": True},
                ]
            )
        elif goal_type == "performance_revision" or domain == "optimization":
            subgoals.extend(
                [
                    {"name": "baseline", "action": "benchmark current", "parallelizable": True},
                    {"name": "apply_changes", "action": "apply optimization", "parallelizable": False},
                    {"name": "verify_improvement", "action": "run benchmarks", "parallelizable": False},
                ]
            )
        else:
            subgoals.extend(
                [
                    {"name": "analyze_goal", "action": "analyze", "parallelizable": True},
                    {"name": "execute_goal", "action": "execute", "parallelizable": False},
                ]
            )
        return subgoals

    def _build_nodes(self, normalized_goal: NormalizedGoal, subgoals: Iterable[Dict[str, object]]) -> List[TaskNode]:
        nodes: List[TaskNode] = []
        produced: Dict[str, str] = {}
        base_requires: List[str] = []
        available_inputs = set(normalized_goal.parameters.keys())
        for idx, subgoal in enumerate(subgoals, start=1):
            name = subgoal["name"]
            description = subgoal["action"]
            tool, args, output = self._select_tool(normalized_goal, subgoal)
            requires = list(base_requires)
            requires.extend(req for req in produced.keys() if not subgoal.get("parallelizable"))
            requires = [req for req in requires if req in produced or req in available_inputs]
            produces_key = output or f"artifact_{idx}_{name}"
            produced[produces_key] = name
            node = TaskNode(
                id=name,
                description=description,
                tool=tool,
                args=args,
                requires=requires,
                produces=[produces_key],
                parallelizable=bool(subgoal.get("parallelizable", False) and self._is_deterministic(tool)),
            )
            nodes.append(node)
            base_requires = [produces_key]
        return nodes

    def _select_tool(self, normalized_goal: NormalizedGoal, subgoal: Dict[str, object]) -> Tuple[Optional[str], Dict[str, object], Optional[str]]:
        goal_text = normalized_goal.raw_text or normalized_goal.as_goal_statement()
        if "open target site" in str(subgoal["action"]) and self.tool_registry.has_tool("browser_agent"):
            url = normalized_goal.parameters.get("target_website", goal_text)
            return "browser_agent", {"mode": "headless", "action": "goto", "url": url}, "loaded_page"
        if "collect page content" in str(subgoal["action"]) and self.tool_registry.has_tool("browser_agent"):
            script = "return document.body ? document.body.innerText.slice(0, 4000) : '';"
            return "browser_agent", {"mode": "headless", "action": "run_js", "script": script}, "page_content"
        if "extract" in str(subgoal["action"]) and self.tool_registry.has_tool("internet_extract"):
            return "internet_extract", {"url": normalized_goal.parameters.get("target_website", goal_text)}, "extracted_content"
        if "design api" in str(subgoal["action"]) and self.tool_registry.has_tool("microservice_builder"):
            return "microservice_builder", {"description": goal_text, "auto_start": False}, "service_spec"
        if "benchmark" in str(subgoal["action"]) and self.tool_registry.has_tool("code_analyzer"):
            output_name = f"{subgoal.get('name', 'benchmark')}_report"
            return "code_analyzer", {"code": goal_text}, output_name
        if "summarize" in str(subgoal["action"]) and self.tool_registry.has_tool("web_search"):
            return "web_search", {"query": goal_text}, "summary"
        if "implement service" in str(subgoal["action"]) and self.tool_registry.has_tool("microservice_builder"):
            args = {"description": goal_text, "auto_start": False}
            args.update({k: v for k, v in normalized_goal.parameters.items() if k in {"endpoint", "resources"}})
            return "microservice_builder", args, "service_instance"
        if "configure ci/cd" in str(subgoal["action"]) and self.tool_registry.has_tool("web_search"):
            return "web_search", {"query": f"ci cd setup {goal_text}"}, "pipeline_guidance"
        return None, {"message": goal_text}, None

    def _is_deterministic(self, tool: Optional[str]) -> bool:
        if tool is None:
            return True
        schema = self.tool_registry.get_schema(tool)
        return bool(schema and schema.deterministic)

    def _attach_validation(self, nodes: List[TaskNode], normalized_goal: NormalizedGoal) -> None:
        if not nodes:
            return
        final_output = nodes[-1].produces[0]
        validation_requires = [final_output]
        validation_node = TaskNode(
            id="validation_checkpoint",
            description="Validate outputs and constraints",
            tool=None,
            args={"constraints": normalized_goal.constraints, "preferences": normalized_goal.preferences},
            requires=validation_requires,
            produces=["validation_report"],
            parallelizable=False,
        )
        test_node = TaskNode(
            id="benchmark_results",
            description="Benchmark and summarize results",
            tool=None,
            args={"baseline": normalized_goal.parameters.get("latest_artifact"), "context": normalized_goal.as_goal_statement()},
            requires=[validation_node.produces[0]],
            produces=["benchmark_summary"],
            parallelizable=True,
        )
        nodes.extend([validation_node, test_node])

    def _build_metadata(
        self, normalized_goal: NormalizedGoal, nodes: List[TaskNode], subgoals: List[Dict[str, object]]
    ) -> Dict[str, object]:
        dependencies = self.world_model.predict_dependencies(normalized_goal.raw_text or normalized_goal.type)
        metadata = {
            "origin_goal": normalized_goal.raw_text or normalized_goal.as_goal_statement(),
            "domain": normalized_goal.domain,
            "preferences": normalized_goal.preferences,
            "constraints": normalized_goal.constraints,
            "parameters": normalized_goal.parameters,
            "subgoals": subgoals,
            "world_model": dependencies,
            "graph_overview": [node.id for node in nodes],
        }
        return metadata
