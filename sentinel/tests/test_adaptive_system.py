import tempfile
import unittest

from sentinel.agent_core.base import ExecutionResult, ExecutionTrace
from sentinel.agent_core.sandbox import Sandbox
from sentinel.memory.intelligence import MemoryContextBuilder, MemoryFilter, MemoryRanker
from sentinel.memory.memory_manager import MemoryManager
from sentinel.planning.adaptive_planner import AdaptivePlanner
from sentinel.planning.task_graph import GraphValidator, TaskGraph, TaskNode, TopologicalExecutor
from sentinel.policy.policy_engine import PolicyEngine
from sentinel.reflection.reflection_engine import ReflectionEngine
from sentinel.tools.registry import ToolRegistry
from sentinel.tools.tool_schema import ToolSchema
from sentinel.agent_core.base import Tool


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

    def execute(self, **kwargs):  # pragma: no cover - simple pass-through
        return kwargs.get("text", "done")


class TestAdaptiveSystem(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.memory = MemoryManager(storage_dir=self.tempdir.name)
        self.registry = ToolRegistry()
        self.registry.register(DummyTool())
        self.policy = PolicyEngine(self.memory, parallel_limit=1)
        self.sandbox = Sandbox()

    def tearDown(self):
        self.tempdir.cleanup()

    def test_adaptive_planner_handles_goal_types(self):
        planner = AdaptivePlanner(self.registry, self.memory, self.policy)
        goals = [
            "Find information about space",
            "Code generation helper",
            "Design microservice for books",
            "Process file report.csv",
        ]
        for goal in goals:
            graph = planner.plan(goal)
            GraphValidator(self.registry).validate(graph)
            self.assertIn("origin_goal", graph.metadata)
            self.assertGreater(len(graph.nodes), 0)

    def test_planner_replans_with_reflection(self):
        planner = AdaptivePlanner(self.registry, self.memory, self.policy)
        base_graph = planner.plan("Fix code bug")
        reflected = {"issues_detected": ["execution_failures"], "plan_adjustment": {"action": "replan"}}
        revised = planner.replan("Fix code bug", reflected)
        self.assertGreaterEqual(len(revised.nodes), len(base_graph.nodes))
        self.assertTrue(any("address_reflection" in node.id for node in revised))

    def test_policy_blocks_disallowed_permission(self):
        risky_tool = DummyTool(name="networker", permissions=["network"])
        self.registry.register(risky_tool)
        graph = TaskGraph([
            TaskNode(
                id="network_task",
                description="attempt risky",
                tool="networker",
                args={},
                produces=["out"],
            )
        ])
        with self.assertRaises(PermissionError):
            self.policy.evaluate_plan(graph, self.registry)

    def test_cycle_denied(self):
        graph = TaskGraph(
            [
                TaskNode(id="a", description="A", tool="dummy", args={}, produces=["x"], requires=["y"]),
                TaskNode(id="b", description="B", tool="dummy", args={}, produces=["y"], requires=["x"]),
            ]
        )
        validator = GraphValidator(self.registry)
        with self.assertRaises(ValueError):
            validator.validate(graph)

    def test_parallel_limit_enforced(self):
        graph = TaskGraph(
            [
                TaskNode(id="a", description="A", tool="dummy", args={}, produces=["x"], parallelizable=True),
                TaskNode(id="b", description="B", tool="dummy", args={}, produces=["y"], parallelizable=True),
            ]
        )
        self.policy.evaluate_plan(graph, self.registry)
        self.assertTrue(all(not node.parallelizable for node in graph))

    def test_memory_intelligence_ranking(self):
        ranker = MemoryRanker(self.memory)
        for idx in range(10):
            self.memory.store_text(f"memory {idx}", namespace="notes", metadata={"tags": "info_query"})
        ranked = ranker.rank("info", "info_query", limit=5)
        filtered = MemoryFilter().filter(ranked)
        builder = MemoryContextBuilder(self.memory, ranker=ranker, mem_filter=MemoryFilter())
        records, context = builder.build_context("info", "info_query", limit=5)
        self.assertLessEqual(len(records), 5)
        self.assertTrue(context == "" or context.startswith("["))
        if filtered:
            self.assertGreaterEqual(filtered[0].score, filtered[-1].score)

    def test_reflection_triggers_replan(self):
        reflection_engine = ReflectionEngine(self.memory, self.policy)
        trace = ExecutionTrace()
        trace.add(ExecutionResult(node=TaskNode(id="n1", description="", tool=None, produces=["x"]), success=False, error="fail"))
        reflection = reflection_engine.reflect(trace, reflection_type="plan-critique", goal="test goal")
        self.assertIn("plan_adjustment", reflection)
        self.assertLessEqual(reflection.get("confidence", 0), 0.8)

    def test_policy_blocks_dangerous_execution(self):
        policy = PolicyEngine(self.memory)
        executor = TopologicalExecutor(self.registry, self.sandbox, memory=self.memory, policy_engine=policy)
        graph = TaskGraph(
            [
                TaskNode(
                    id="danger",
                    description="",
                    tool="dummy",
                    args={"text": "use subprocess"},
                    produces=["out"],
                )
            ]
        )
        trace = executor.execute(graph)
        self.assertTrue(trace.failed_nodes)

    def test_planner_emits_tool_gap_when_no_tools_match(self):
        empty_registry = ToolRegistry()
        planner = AdaptivePlanner(empty_registry, self.memory, self.policy)
        graph = planner.plan("Navigate a complex web form")

        gaps = graph.metadata.get("tool_gaps", [])
        self.assertTrue(gaps)
        self.assertTrue(all(gap.get("requested_tool") for gap in gaps))

        plan_records = self.memory.query("plans")
        self.assertTrue(any("tool_gap" in str(record.get("value", {})) for record in plan_records))

        policy_events = self.memory.query("policy_events")
        self.assertTrue(any("tool_gap" in str(event.get("value", {})) for event in policy_events))

        for node in graph:
            if node.tool is not None:
                self.assertTrue(empty_registry.has_tool(node.tool))


if __name__ == "__main__":
    unittest.main()
