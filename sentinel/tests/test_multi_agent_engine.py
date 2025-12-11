import tempfile
import unittest

from sentinel.agent_core.base import Tool
from sentinel.dialog_manager import DialogManager
from sentinel.memory.memory_manager import MemoryManager
from sentinel.planning.adaptive_planner import AdaptivePlanner
from sentinel.planning.task_graph import TaskGraph, TaskNode
from sentinel.policy.policy_engine import PolicyEngine
from sentinel.simulation.sandbox import SimulationSandbox
from sentinel.tools.registry import ToolRegistry
from sentinel.tools.tool_autonomy_policy import ToolAutonomyPolicy
from sentinel.tools.tool_schema import ToolSchema
from sentinel.agents.multi_agent_engine import MultiAgentEngine, ToolEvolutionAgent
from sentinel.world.model import WorldModel


class DummyTool(Tool):
    def __init__(self, name: str = "dummy", deterministic: bool = True, permissions=None):
        super().__init__(name=name, description="dummy", deterministic=deterministic)
        self.schema = ToolSchema(
            name=name,
            version="0.0.1",
            description="dummy",
            input_schema={"text": {"type": "string", "required": False}},
            output_schema={"text": "string"},
            permissions=permissions or ["read"],
            deterministic=deterministic,
        )

    def execute(self, **kwargs):  # pragma: no cover - pass-through
        return kwargs.get("text", "done")


class TestMultiAgentEngine(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.memory = MemoryManager(storage_dir=self.tempdir.name)
        self.registry = ToolRegistry()
        self.registry.register(DummyTool(name="baseline"))
        self.policy = PolicyEngine(self.memory)
        self.world_model = WorldModel(self.memory)
        self.sandbox = SimulationSandbox(self.registry)
        self.dialog_manager = DialogManager(self.memory, self.world_model)
        self.planner = AdaptivePlanner(self.registry, self.memory, self.policy)
        self.autonomy_policy = ToolAutonomyPolicy(autonomy_mode="autonomous")
        self.engine = MultiAgentEngine(
            planner=self.planner,
            registry=self.registry,
            sandbox=self.sandbox,
            memory=self.memory,
            policy_engine=self.policy,
            world_model=self.world_model,
            dialog_manager=self.dialog_manager,
            autonomy_policy=self.autonomy_policy,
        )

    def tearDown(self):
        self.tempdir.cleanup()

    def test_missing_tool_triggers_gap_detection(self):
        graph = TaskGraph(
            [
                TaskNode(id="a", description="needs tool", tool="unknown_tool", args={}, produces=["x"]),
                TaskNode(id="b", description="no tool", tool=None, args={}, produces=["y"], requires=["x"]),
            ]
        )
        gap = self.engine.evaluate_tool_gaps(graph, self.world_model)
        self.assertIsNotNone(gap)
        self.assertIn("Missing tool", gap)

    def test_simulation_failure_rejects_candidate(self):
        evolution_agent = self.engine.tool_evolution_agent
        spec = {
            "name": "sim_fail_tool",
            "version": "0.0.1",
            "description": "fails simulation",
            "input_schema": {"instruction": {"type": "string", "required": True}},
            "output_schema": {"echo": "string"},
            "permissions": ["read"],
            "sample_args": {},
        }
        metrics = evolution_agent.simulate_and_benchmark(spec)
        metrics["comparison"] = {"better_or_equal": True}
        decision = evolution_agent.decide_acceptance(metrics, "autonomous")
        self.assertFalse(decision["accepted"])
        self.assertEqual(decision["reason"], "simulation_failure")

    def test_benchmark_regression_rejected(self):
        evolution_agent = self.engine.tool_evolution_agent
        metrics = {
            "simulation": {"success": True, "warnings": [], "benchmark": {"relative_speed": 1}},
            "policy_allowed": True,
            "comparison": {"better_or_equal": False},
            "tool_spec": {
                "name": "slow_tool",
                "version": "0.0.1",
                "description": "slow", 
                "input_schema": {},
                "output_schema": {},
                "permissions": ["read"],
                "deterministic": True,
            },
        }
        decision = evolution_agent.decide_acceptance(metrics, "autonomous")
        self.assertFalse(decision["accepted"])
        self.assertEqual(decision["reason"], "policy_or_benchmark_block")

    def test_autonomy_modes_require_confirmation(self):
        evolution_agent = self.engine.tool_evolution_agent
        metrics = {
            "simulation": {"success": True, "warnings": [], "benchmark": {"relative_speed": 5}},
            "policy_allowed": True,
            "comparison": {"better_or_equal": True},
            "tool_spec": {
                "name": "consent_tool",
                "version": "0.0.1",
                "description": "needs consent",
                "input_schema": {},
                "output_schema": {},
                "permissions": ["read"],
                "deterministic": True,
            },
        }
        ask_decision = evolution_agent.decide_acceptance(metrics, "ask")
        self.assertFalse(ask_decision["accepted"])
        self.assertEqual(ask_decision["integration"], "pending_user")

        review_decision = evolution_agent.decide_acceptance(metrics, "review")
        self.assertFalse(review_decision["accepted"])
        self.assertEqual(review_decision["integration"], "pending_review")

    def test_autonomous_mode_registers_tool(self):
        evolution_agent = self.engine.tool_evolution_agent
        spec = {
            "name": "auto_candidate",
            "version": "0.1.0",
            "description": "auto candidate",
            "input_schema": {"instruction": {"type": "string", "required": False}},
            "output_schema": {"echo": "object"},
            "permissions": ["read"],
            "deterministic": True,
            "sample_args": {"instruction": "demo"},
        }
        metrics = evolution_agent.simulate_and_benchmark(spec)
        metrics["comparison"] = {"better_or_equal": True}
        decision = evolution_agent.decide_acceptance(metrics, "autonomous")
        self.assertTrue(decision["accepted"])
        self.assertTrue(self.registry.has_tool("auto_candidate"))


if __name__ == "__main__":
    unittest.main()
