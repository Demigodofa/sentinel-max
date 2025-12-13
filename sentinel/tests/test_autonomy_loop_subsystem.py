from sentinel.agent_core.autonomy import AutonomyLoop
from sentinel.agent_core.base import ExecutionResult, ExecutionTrace
from sentinel.agent_core.reflection import Reflector
from sentinel.agent_core.worker import Worker
from sentinel.execution.execution_controller import ExecutionController
from sentinel.memory.memory_manager import MemoryManager
from sentinel.planning.task_graph import TaskGraph, TaskNode
from sentinel.policy.policy_engine import PolicyEngine
from sentinel.reflection.reflection_engine import ReflectionEngine
from sentinel.agent_core.sandbox import Sandbox
from sentinel.tools.registry import ToolRegistry


class _StubWorker(Worker):
    def __init__(self):
        registry = ToolRegistry()
        super().__init__(registry, Sandbox())

    def run(self, graph: TaskGraph, correlation_id=None):
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
