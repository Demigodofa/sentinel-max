"""Multi-agent coordination layer for Sentinel MAX."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

from sentinel.agent_core.base import Tool
from sentinel.dialog_manager import DialogManager
from sentinel.memory.memory_manager import MemoryManager
from sentinel.planning.adaptive_planner import AdaptivePlanner
from sentinel.planning.task_graph import TaskGraph
from sentinel.policy.policy_engine import PolicyEngine
from sentinel.simulation.sandbox import SimulationResult, SimulationSandbox
from sentinel.tools.registry import ToolRegistry
from sentinel.tools.tool_autonomy_policy import ToolAutonomyPolicy
from sentinel.tools.tool_schema import ToolSchema
from sentinel.world.model import WorldModel


@dataclass
class CriticFeedback:
    issues: List[str] = field(default_factory=list)
    missing_tools: List[str] = field(default_factory=list)
    redundant_steps: List[str] = field(default_factory=list)
    missing_dependencies: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)


@dataclass
class OptimizationSuggestion:
    description: str
    apply: bool = True
    target_nodes: List[str] = field(default_factory=list)


class PlannerAgent:
    """Generates first-pass task graphs and capability requirements."""

    def __init__(
        self,
        planner: AdaptivePlanner,
        memory: MemoryManager,
        dialog_manager: DialogManager,
        world_model: WorldModel,
    ) -> None:
        self.planner = planner
        self.memory = memory
        self.dialog_manager = dialog_manager
        self.world_model = world_model

    def build_plan(self, normalized_goal: str) -> TaskGraph:
        context = self.dialog_manager.build_context(normalized_goal)
        domain_capabilities = self.world_model.list_capabilities(context["domain"])
        graph = self.planner.plan(normalized_goal)
        graph.add_metadata(
            origin_goal=normalized_goal,
            dialog_context=context,
            domain_capabilities=domain_capabilities,
        )
        return graph


class CriticAgent:
    """Evaluates candidate task graphs for gaps and risks."""

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def evaluate(self, graph: TaskGraph) -> CriticFeedback:
        issues: List[str] = []
        missing_tools: List[str] = []
        redundant_steps: List[str] = []
        missing_dependencies: List[str] = []
        suggestions: List[str] = []

        produced: set[str] = set()
        for node in graph:
            produced.update(node.produces)

        for node in graph:
            if node.tool and not self.registry.has_tool(node.tool):
                missing_tools.append(node.tool)
                issues.append(f"Task {node.id} references unknown tool {node.tool}")
            if not node.tool:
                issues.append(f"Task {node.id} has no tool specified")
            for requirement in node.requires:
                if requirement not in produced:
                    missing_dependencies.append(requirement)
            if node.parallelizable and node.requires:
                suggestions.append(f"Task {node.id} may need serialization due to dependencies")

        seen_descriptions: set[str] = set()
        for node in graph:
            if node.description in seen_descriptions:
                redundant_steps.append(node.id)
            seen_descriptions.add(node.description)

        return CriticFeedback(
            issues=sorted(set(issues)),
            missing_tools=sorted(set(missing_tools)),
            redundant_steps=sorted(set(redundant_steps)),
            missing_dependencies=sorted(set(missing_dependencies)),
            suggestions=sorted(set(suggestions)),
        )


class SimulationAgent:
    """Simulates task graphs using the in-memory sandbox."""

    def __init__(self, sandbox: SimulationSandbox, world_model: WorldModel):
        self.sandbox = sandbox
        self.world_model = world_model

    def simulate(self, graph: TaskGraph) -> Dict[str, SimulationResult]:
        return self.sandbox.simulate_taskgraph(graph, self.world_model)


class OptimizationAgent:
    """Suggests plan optimizations based on simulations."""

    def suggest(
        self, graph: TaskGraph, simulations: Dict[str, SimulationResult]
    ) -> List[OptimizationSuggestion]:
        suggestions: List[OptimizationSuggestion] = []
        for node in graph:
            sim = simulations.get(node.id)
            if sim and sim.benchmark.get("relative_speed", 0) <= 3:
                suggestions.append(
                    OptimizationSuggestion(
                        description=f"Parallelize or simplify slow node {node.id}",
                        target_nodes=[node.id],
                    )
                )
            if sim and sim.warnings:
                suggestions.append(
                    OptimizationSuggestion(
                        description=f"Address warnings for {node.id}: {', '.join(sim.warnings)}",
                        target_nodes=[node.id],
                    )
                )
        return suggestions


class ResearchAgent:
    """Supplies external knowledge when planning context is insufficient."""

    def __init__(self, memory: MemoryManager, world_model: WorldModel) -> None:
        self.memory = memory
        self.world_model = world_model

    def research(self, topic: str) -> Dict[str, Any]:
        domain = self.world_model.get_domain(topic)
        capabilities = self.world_model.list_capabilities(domain.name)
        summary = {
            "topic": topic,
            "domain": domain.name,
            "capability_summary": capabilities,
            "recommended_transformations": [
                "decompose goal into capability-aligned subtasks",
                "prefer deterministic tools for first iteration",
            ],
        }
        self.memory.store_fact(
            "research",
            key=None,
            value=summary,
            metadata={"source": "research_agent", "topic": topic},
        )
        return summary


class CandidateTool(Tool):
    """Lightweight tool used for in-memory evolution and simulation."""

    def __init__(self, schema: ToolSchema) -> None:
        super().__init__(name=schema.name, description=schema.description, deterministic=schema.deterministic)
        self.schema = schema

    def execute(self, **kwargs: Any) -> Any:  # pragma: no cover - safe echo
        return {"echo": kwargs, "tool": self.name}


class ToolEvolutionAgent:
    """Discovers, simulates, and governs tool evolution."""

    def __init__(
        self,
        registry: ToolRegistry,
        sandbox: SimulationSandbox,
        policy_engine: PolicyEngine,
        memory: MemoryManager,
        world_model: WorldModel,
        autonomy_policy: ToolAutonomyPolicy,
    ) -> None:
        self.registry = registry
        self.sandbox = sandbox
        self.policy_engine = policy_engine
        self.memory = memory
        self.world_model = world_model
        self.autonomy_policy = autonomy_policy

    def detect_missing_tool(self, taskgraph: TaskGraph) -> Optional[str]:
        for node in taskgraph:
            if node.tool and not self.registry.has_tool(node.tool):
                return f"Missing tool: {node.tool} for task {node.id}"
            if not node.tool:
                return f"Task {node.id} lacks a bound tool"
        return None

    def generate_tool_spec(self, gap: str) -> Dict[str, Any]:
        domain = self.world_model.get_domain(gap)
        capabilities = self.world_model.list_capabilities(domain.name)
        name = f"auto_{domain.name}_helper"
        spec = {
            "name": name,
            "version": "0.1.0",
            "description": f"Automated tool generated to close gap: {gap}",
            "input_schema": {"instruction": {"type": "string", "required": True}},
            "output_schema": {"echo": "object"},
            "permissions": ["read", "analyze"],
            "deterministic": True,
            "capabilities": capabilities,
            "gap": gap,
            "sample_args": {"instruction": gap},
        }
        self.memory.store_fact(
            "tool_evolution",
            key=None,
            value={"event": "generated_spec", "spec": spec},
            metadata={"gap": gap},
        )
        return spec

    def simulate_and_benchmark(self, tool_spec: Dict[str, Any]) -> Dict[str, Any]:
        schema = ToolSchema(
            name=tool_spec["name"],
            version=tool_spec.get("version", "0.0.1"),
            description=tool_spec.get("description", tool_spec["name"]),
            input_schema=tool_spec.get("input_schema", {}),
            output_schema=tool_spec.get("output_schema", {}),
            permissions=tool_spec.get("permissions", ["read"]),
            deterministic=tool_spec.get("deterministic", True),
        )
        candidate_tool = CandidateTool(schema)
        scratch_registry = ToolRegistry()
        scratch_registry.register(candidate_tool)
        scratch_sandbox = SimulationSandbox(scratch_registry)
        sample_args = tool_spec.get("sample_args", {})
        simulation = scratch_sandbox.simulate_tool_call(schema.name, sample_args, self.world_model)
        metrics = {
            "simulation": {
                "success": simulation.success,
                "warnings": simulation.warnings,
                "benchmark": simulation.benchmark,
            },
            "policy_allowed": self._policy_check(schema.permissions),
            "tool_spec": tool_spec,
        }
        return metrics

    def compare_with_existing(
        self, tool_spec: Dict[str, Any], metrics: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        comparison: Dict[str, Any] = {"better_or_equal": True, "relative_change": 0}
        baseline_name = tool_spec.get("baseline_tool")
        if baseline_name and self.registry.has_tool(baseline_name):
            baseline_schema = self.registry.get_schema(baseline_name)
            baseline_speed = 5
            if baseline_schema:
                baseline_sim = self.sandbox.simulate_tool_call(baseline_schema.name, {}, self.world_model)
                baseline_speed = baseline_sim.benchmark.get("relative_speed", 5)
            candidate_speed = 0
            if metrics:
                candidate_speed = metrics.get("simulation", {}).get("benchmark", {}).get("relative_speed", 0)
            if not candidate_speed:
                candidate_speed = tool_spec.get("benchmark", {}).get("relative_speed", 0)
            comparison["relative_change"] = candidate_speed - baseline_speed
            comparison["better_or_equal"] = candidate_speed >= baseline_speed
        return comparison

    def decide_acceptance(self, metrics: Dict[str, Any], autonomy_mode: Literal["ask", "review", "autonomous"]) -> Dict[str, Any]:
        simulation_ok = not self.autonomy_policy.require_simulation_success or (
            metrics["simulation"]["success"] and not metrics["simulation"].get("warnings")
        )
        policy_ok = not self.autonomy_policy.require_policy_approval or metrics.get("policy_allowed", False)
        comparison = metrics.get("comparison", {"better_or_equal": True})
        benchmark_ok = not self.autonomy_policy.require_benchmark_improvement or comparison.get("better_or_equal", False)

        accepted = simulation_ok and policy_ok and benchmark_ok
        decision: Dict[str, Any] = {
            "accepted": False,
            "autonomy_mode": autonomy_mode,
            "reason": "",
            "integration": None,
        }

        if not accepted:
            decision["reason"] = "simulation_failure" if not simulation_ok else "policy_or_benchmark_block"
            self._record_decision("rejected", metrics, decision["reason"])
            return decision

        if autonomy_mode == "ask":
            decision.update({"accepted": False, "reason": "user_confirmation_required", "integration": "pending_user"})
            self._record_decision("awaiting_user", metrics, decision["reason"])
            return decision

        if autonomy_mode == "review":
            decision.update({"accepted": False, "reason": "review_required", "integration": "pending_review"})
            self._record_decision("awaiting_review", metrics, decision["reason"])
            return decision

        tool_spec = metrics.get("tool_spec", {})
        integration = self._register_candidate(tool_spec)
        decision.update({"accepted": True, "reason": "autonomous_accept", "integration": integration})
        self._record_decision("accepted", metrics, decision["reason"])
        return decision

    def _policy_check(self, permissions: List[str]) -> bool:
        allowed = self.policy_engine.allowed_permissions if hasattr(self.policy_engine, "allowed_permissions") else set()
        if not allowed:
            return True
        return set(permissions).issubset(set(allowed))

    def _register_candidate(self, tool_spec: Dict[str, Any]) -> Optional[str]:
        try:
            schema = ToolSchema(
                name=tool_spec["name"],
                version=tool_spec.get("version", "0.0.1"),
                description=tool_spec.get("description", tool_spec["name"]),
                input_schema=tool_spec.get("input_schema", {}),
                output_schema=tool_spec.get("output_schema", {}),
                permissions=tool_spec.get("permissions", ["read"]),
                deterministic=tool_spec.get("deterministic", True),
            )
            tool = CandidateTool(schema)
            self.registry.register(tool)
            return tool.name
        except Exception as exc:  # pragma: no cover - defensive
            self._record_decision("integration_failed", {"tool_spec": tool_spec, "error": str(exc)}, "integration_error")
            return None

    def _record_decision(self, event: str, payload: Dict[str, Any], reason: str) -> None:
        self.memory.store_fact(
            "tool_evolution",
            key=None,
            value={"event": event, "payload": payload, "reason": reason},
            metadata={"source": "tool_evolution_agent"},
        )


class MultiAgentEngine:
    """Coordinates planner, critic, simulation, optimization, and tool evolution."""

    def __init__(
        self,
        planner: AdaptivePlanner,
        registry: ToolRegistry,
        sandbox: SimulationSandbox,
        memory: MemoryManager,
        policy_engine: PolicyEngine,
        world_model: WorldModel,
        dialog_manager: DialogManager,
        autonomy_policy: Optional[ToolAutonomyPolicy] = None,
    ) -> None:
        self.registry = registry
        self.sandbox = sandbox
        self.memory = memory
        self.policy_engine = policy_engine
        self.world_model = world_model
        self.dialog_manager = dialog_manager
        self.autonomy_policy = autonomy_policy or ToolAutonomyPolicy(autonomy_mode="ask")

        self.planner_agent = PlannerAgent(planner, memory, dialog_manager, world_model)
        self.critic_agent = CriticAgent(registry)
        self.simulation_agent = SimulationAgent(sandbox, world_model)
        self.optimization_agent = OptimizationAgent()
        self.research_agent = ResearchAgent(memory, world_model)
        self.tool_evolution_agent = ToolEvolutionAgent(
            registry, sandbox, policy_engine, memory, world_model, self.autonomy_policy
        )

    def assess_goal(self, normalized_goal: str, world_model: WorldModel) -> Dict[str, Any]:
        domain = world_model.get_domain(normalized_goal)
        capabilities = world_model.list_capabilities(domain.name)
        resources = world_model.predict_required_resources(normalized_goal)
        dependencies = world_model.predict_dependencies(normalized_goal)
        assessment = {
            "goal": normalized_goal,
            "domain": domain.name,
            "capabilities": capabilities,
            "resources": [res.name for res in resources],
            "dependencies": dependencies,
        }
        self.memory.store_fact(
            "goal_assessments",
            key=None,
            value=assessment,
            metadata={"source": "multi_agent_engine"},
        )
        return assessment

    def propose_plan(self, goal: str) -> TaskGraph:
        return self.planner_agent.build_plan(goal)

    def evaluate_plan(self, taskgraph: TaskGraph) -> CriticFeedback:
        feedback = self.critic_agent.evaluate(taskgraph)
        self.memory.store_fact(
            "plan_feedback",
            key=None,
            value=feedback.__dict__,
            metadata={"source": "critic_agent"},
        )
        return feedback

    def evaluate_tool_gaps(self, taskgraph: TaskGraph, world_model: WorldModel) -> Optional[str]:
        gap = self.tool_evolution_agent.detect_missing_tool(taskgraph)
        if gap:
            self.memory.store_fact(
                "tool_evolution",
                key=None,
                value={"event": "gap_detected", "gap": gap, "domain": world_model.get_domain(gap).name},
                metadata={"source": "multi_agent_engine"},
            )
        return gap

    def propose_new_tool(self, gap_description: str) -> Dict[str, Any]:
        return self.tool_evolution_agent.generate_tool_spec(gap_description)

    def evaluate_tool_candidate(self, tool_spec: Dict[str, Any]) -> Dict[str, Any]:
        metrics = self.tool_evolution_agent.simulate_and_benchmark(tool_spec)
        metrics["comparison"] = self.tool_evolution_agent.compare_with_existing(tool_spec, metrics)
        return metrics

    def apply_tool_autonomy(self, candidate_tool: Dict[str, Any], metrics: Dict[str, Any]) -> Dict[str, Any]:
        metrics["tool_spec"] = candidate_tool
        return self.tool_evolution_agent.decide_acceptance(metrics, self.autonomy_policy.autonomy_mode)

    def apply_critic_feedback(self, plan: TaskGraph, feedback: CriticFeedback) -> TaskGraph:
        if feedback.missing_dependencies:
            plan.add_metadata(missing_dependencies=feedback.missing_dependencies)
        if feedback.suggestions:
            plan.add_metadata(critic_suggestions=feedback.suggestions)
        return plan

    def apply_optimizations(self, plan: TaskGraph, optimizations: List[OptimizationSuggestion]) -> TaskGraph:
        for suggestion in optimizations:
            if suggestion.apply:
                for node_id in suggestion.target_nodes:
                    if node_id in plan.nodes:
                        plan.nodes[node_id].parallelizable = True
        if optimizations:
            plan.add_metadata(optimizations=[opt.description for opt in optimizations])
        return plan

    def coordinate(self, normalized_goal: str | TaskGraph) -> TaskGraph:
        if isinstance(normalized_goal, TaskGraph):
            plan = normalized_goal
        else:
            plan = self.planner_agent.build_plan(normalized_goal)
        criticisms = self.critic_agent.evaluate(plan)
        plan = self.apply_critic_feedback(plan, criticisms)
        simulations = self.simulation_agent.simulate(plan)
        optimizations = self.optimization_agent.suggest(plan, simulations)
        plan = self.apply_optimizations(plan, optimizations)
        gap = self.tool_evolution_agent.detect_missing_tool(plan)
        if gap:
            tool_spec = self.tool_evolution_agent.generate_tool_spec(gap)
            metrics = self.evaluate_tool_candidate(tool_spec)
            self.tool_evolution_agent.decide_acceptance(metrics, self.autonomy_policy.autonomy_mode)
        return plan
