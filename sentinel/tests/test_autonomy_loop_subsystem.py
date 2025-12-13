from sentinel.agent_core.autonomy import AutonomyLoop
from sentinel.agent_core.base import ExecutionResult, ExecutionTrace
from sentinel.agent_core.reflection import Reflector
from sentinel.agent_core.worker import Worker
from sentinel.execution.execution_controller import ExecutionController, ExecutionMode
from sentinel.memory.memory_manager import MemoryManager
from sentinel.planning.adaptive_planner import AdaptivePlanner
from sentinel.planning.task_graph import TaskGraph, TaskNode
from sentinel.policy.policy_engine import PolicyEngine
from sentinel.reflection.reflection_engine import ReflectionEngine
from sentinel.agent_core.sandbox import Sandbox
from sentinel.tools.registry import ToolRegistry


class _StubWorker(Worker):
    def __init__(self):
        registry = ToolRegistry()
        super().__init__(registry, Sandbox())

    def run(self, graph: TaskGraph):
        trace = ExecutionTrace()
        for node in graph:
            trace.add(ExecutionResult(node=node, success=True, output=node.id))
        trace.batches.append([node.id for node in graph])
        return trace


class _StubExecutionController(ExecutionController):
    def __init__(self, worker: Worker, memory: MemoryManager, policy: PolicyEngine):
        super().__init__(worker, policy, None, None, memory)

    def request_execution(self, taskgraph, mode, parameters):
        return self.worker.run(taskgraph)


class _ReplayExecutionController(ExecutionController):
    def __init__(
        self, worker: Worker, memory: MemoryManager, policy: PolicyEngine, traces: list[ExecutionTrace]
    ) -> None:
        super().__init__(worker, policy, None, None, memory)
        self.traces = traces
        self.calls = 0

    def request_execution(self, taskgraph, mode, parameters):  # pragma: no cover - controlled in tests
        idx = min(self.calls, len(self.traces) - 1)
        self.calls += 1
        return self.traces[idx]


def test_autonomy_loop_runs_graph_and_records_reflection(tmp_path):
    memory = MemoryManager(storage_dir=tmp_path)
    worker = _StubWorker()
    policy = PolicyEngine()
    reflector = Reflector(memory, ReflectionEngine(memory, policy_engine=policy))
    execution_controller = _StubExecutionController(worker, memory, policy)
    autonomy = AutonomyLoop(
        planner=None,  # not used in run_graph
        worker=worker,
        execution_controller=execution_controller,
        reflector=reflector,
        memory=memory,
    )

    graph = TaskGraph([TaskNode("n1", "", None, produces=["out"])])
    trace = autonomy.run_graph(graph, goal="demo")

    assert trace.results and trace.results[0].output == "n1"
    assert autonomy.last_reflection is not None


def test_failed_step_triggers_replan_and_updated_reflection(tmp_path):
    memory = MemoryManager(storage_dir=tmp_path)
    worker = _StubWorker()
    policy = PolicyEngine(memory)
    planner = AdaptivePlanner(worker.tool_registry, memory, policy)
    reflector = Reflector(memory, ReflectionEngine(memory, policy_engine=policy))

    failing_trace = ExecutionTrace()
    failing_trace.add(ExecutionResult(node=TaskNode("failed", "", None, produces=["x"]), success=False, error="boom"))
    success_trace = ExecutionTrace()
    success_trace.add(ExecutionResult(node=TaskNode("recover", "", None, produces=["y"]), success=True, output="ok"))

    execution_controller = _ReplayExecutionController(worker, memory, policy, [failing_trace, success_trace])
    autonomy = AutonomyLoop(
        planner=planner,
        worker=worker,
        execution_controller=execution_controller,
        reflector=reflector,
        memory=memory,
        cycle_limit=3,
    )

    trace = autonomy.run("demo goal", ExecutionMode.UNTIL_COMPLETE, parameters={})

    assert execution_controller.calls == 2
    assert trace.failed_nodes == []
    assert autonomy.last_reflection is not None
    assert autonomy.last_reflection.get("issues_detected") == []
    plan_versions = {
        entry.get("value", {}).get("version")
        for entry in memory.query("plans")
        if isinstance(entry.get("value"), dict) and entry.get("value", {}).get("goal") == "demo goal"
    }
    assert max(plan_versions) == 2


def test_autonomy_records_cycles_and_honors_failure_limit(tmp_path):
    memory = MemoryManager(storage_dir=tmp_path)
    worker = _StubWorker()
    policy = PolicyEngine(memory)
    planner = AdaptivePlanner(worker.tool_registry, memory, policy)
    reflector = Reflector(memory, ReflectionEngine(memory, policy_engine=policy))

    failing_trace = ExecutionTrace()
    failing_trace.add(ExecutionResult(node=TaskNode("failed", "", None, produces=["x"]), success=False, error="boom"))
    another_fail = ExecutionTrace()
    another_fail.add(ExecutionResult(node=TaskNode("failed_again", "", None, produces=["y"]), success=False, error="still boom"))

    execution_controller = _ReplayExecutionController(worker, memory, policy, [failing_trace, another_fail])
    autonomy = AutonomyLoop(
        planner=planner,
        worker=worker,
        execution_controller=execution_controller,
        reflector=reflector,
        memory=memory,
        cycle_limit=5,
        max_failed_cycles=2,
    )

    trace = autonomy.run("failing goal", ExecutionMode.UNTIL_COMPLETE, parameters={})

    cycles = memory.query("autonomy.cycles")
    assert execution_controller.calls == 2
    assert len(cycles) == 2
    assert trace.failed_nodes  # final trace is the last failed run before hitting the failure limit
    plan_versions = {entry.get("value", {}).get("plan_version") for entry in cycles}
    assert plan_versions == {1, 2}
    assert any(entry.get("value", {}).get("replan_requested") for entry in cycles)
