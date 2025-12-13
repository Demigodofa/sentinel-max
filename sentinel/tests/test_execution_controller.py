import time
import unittest
import tempfile

from sentinel.agent_core.base import ExecutionResult
from sentinel.agent_core.sandbox import Sandbox
from sentinel.execution.approval_gate import ApprovalGate
from sentinel.execution.execution_controller import ExecutionController
from sentinel.dialog_manager import DialogManager
from sentinel.memory.memory_manager import MemoryManager
from sentinel.planning.task_graph import TaskGraph, TaskNode
from sentinel.policy.policy_engine import PolicyEngine
from sentinel.tools.registry import ToolRegistry
from sentinel.tools.tool_schema import ToolSchema
from sentinel.agent_core.worker import Worker
from sentinel.world.model import WorldModel
from sentinel.agent_core.base import Tool


class DummyTool(Tool):
    def __init__(self, name: str = "dummy", delay: float = 0.0):
        super().__init__(name=name, description="dummy")
        self.delay = delay
        self.schema = ToolSchema(
            name=name,
            version="0.0.1",
            description="dummy",
            input_schema={"text": {"type": "string", "required": False}},
            output_schema={"text": "string"},
            permissions=["read"],
            deterministic=True,
        )

    def execute(self, **kwargs):  # pragma: no cover - simple deterministic execution
        if self.delay:
            time.sleep(self.delay)
        return kwargs.get("text", "done")


class RecordingDialogManager(DialogManager):
    def __init__(self, memory: MemoryManager, world_model: WorldModel):
        super().__init__(memory, world_model)
        self.prompts: list[str] = []
        self.notifications: list[dict] = []

    def prompt_execution_approval(self, description: str):  # pragma: no cover - simple recording
        self.prompts.append(description)
        return super().prompt_execution_approval(description)

    def notify_execution_status(self, status: dict):  # pragma: no cover - simple recording
        self.notifications.append(status)
        return super().notify_execution_status(status)


class TestExecutionController(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.memory = MemoryManager(storage_dir=self.tempdir.name)
        self.world_model = WorldModel(self.memory)
        self.registry = ToolRegistry()
        self.registry.register(DummyTool())
        self.policy = PolicyEngine(self.memory, max_execution_time=5, max_cycles=10)
        self.sandbox = Sandbox()
        self.dialog = RecordingDialogManager(self.memory, self.world_model)
        self.approval = ApprovalGate(self.dialog)
        self.worker = Worker(
            self.registry,
            self.sandbox,
            memory=self.memory,
            policy_engine=self.policy,
            approval_gate=self.approval,
        )
        self.controller = ExecutionController(
            self.worker, self.policy, self.approval, self.dialog, self.memory
        )

    def tearDown(self):
        self.tempdir.cleanup()

    def _graph_two_steps(self, delay: float = 0.0, first_delay: float = 0.0):
        if delay:
            slow_tool = DummyTool(name="slow", delay=delay)
            self.registry.register(slow_tool)
        if first_delay:
            slow_first = DummyTool(name="slow_first", delay=first_delay)
            self.registry.register(slow_first)
        nodes = [
            TaskNode(
                id="a",
                description="first",
                tool="slow_first" if first_delay else "dummy",
                produces=["x"],
                args={},
            ),
            TaskNode(id="b", description="second", tool="slow" if delay else "dummy", requires=["x"], produces=["y"]),
        ]
        return TaskGraph(nodes)

    def test_until_complete_executes_all_nodes(self):
        self.approval.approve()
        graph = self._graph_two_steps()
        trace = self.controller.execute_until_complete(graph)
        self.assertEqual(len(trace.results), 2)
        self.assertTrue(all(isinstance(res, ExecutionResult) for res in trace.results))

    def test_for_time_stops_after_seconds(self):
        self.approval.approve()
        graph = self._graph_two_steps(delay=0.2, first_delay=0.2)
        trace = self.controller.execute_for_time(graph, seconds=0.05)
        self.assertLess(len(trace.results), len(graph.nodes))

    def test_until_node_halts_after_target(self):
        self.approval.approve()
        graph = self._graph_two_steps()
        trace = self.controller.execute_until_node(graph, target_node_id="a")
        self.assertEqual(trace.results[-1].node.id, "a")
        self.assertEqual(len(trace.results), 1)

    def test_policy_block_reasons_are_recorded(self):
        self.approval.approve()
        self.policy.real_tool_allowlist = {"other"}
        graph = self._graph_two_steps()
        trace = self.controller.execute_until_complete(graph)
        self.assertTrue(trace.results)
        first_result = trace.results[0]
        self.assertFalse(first_result.success)
        self.assertIsNotNone(first_result.policy)
        self.assertIn("not allowed", " ".join(first_result.policy.reasons))

    def test_for_cycles_limits_executions(self):
        self.approval.approve()
        graph = self._graph_two_steps()
        trace = self.controller.execute_for_cycles(graph, max_cycles=1)
        self.assertEqual(len(trace.results), 1)

    def test_until_condition_respects_predicate(self):
        self.approval.approve()
        graph = self._graph_two_steps()
        trace = self.controller.execute_until_condition(graph, lambda t: len(t.results) >= 1)
        self.assertEqual(len(trace.results), 1)

    def test_with_checkins_emits_notifications(self):
        self.approval.approve()
        graph = self._graph_two_steps()
        trace = self.controller.execute_with_checkins(graph, interval_seconds=0.01)
        self.assertGreaterEqual(len(self.dialog.notifications), 1)
        self.assertEqual(len(trace.results), len(graph.nodes))

    def test_denied_approval_blocks_execution(self):
        graph = self._graph_two_steps()
        trace = self.controller.execute_until_complete(graph)
        self.assertTrue(trace.results)
        self.assertFalse(trace.results[0].success)
        self.assertIn("Approval", trace.results[0].error)

    def test_policy_restricts_real_execution(self):
        restricted_policy = PolicyEngine(
            self.memory, max_execution_time=5, max_cycles=5, real_tool_allowlist={"other"}
        )
        worker = Worker(
            self.registry,
            self.sandbox,
            memory=self.memory,
            policy_engine=restricted_policy,
            approval_gate=self.approval,
        )
        controller = ExecutionController(worker, restricted_policy, self.approval, self.dialog, self.memory)
        self.approval.approve()
        graph = self._graph_two_steps()
        trace = controller.execute_until_complete(graph)
        self.assertFalse(trace.results[0].success)
        self.assertIn("not allowed", trace.results[0].error)

    def test_worker_stores_real_execution_metadata(self):
        self.approval.approve()
        graph = self._graph_two_steps()
        self.controller.execute_until_complete(graph)
        records = self.memory.query("execution_real")
        self.assertTrue(records)
        self.assertIn("task", records[0].get("value", {}))


if __name__ == "__main__":
    unittest.main()
