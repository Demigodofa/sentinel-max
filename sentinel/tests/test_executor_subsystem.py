from sentinel.agent_core.sandbox import Sandbox
from sentinel.planning.task_graph import TaskGraph, TaskNode, TopologicalExecutor
from sentinel.tools.registry import ToolRegistry
from sentinel.tools.tool_schema import ToolSchema
from sentinel.agent_core.base import Tool


class _AddTool(Tool):
    def __init__(self):
        super().__init__("adder", deterministic=True)
        self.schema = ToolSchema(
            name="adder",
            version="1.0.0",
            description="add",
            input_schema={},
            output_schema={},
            permissions=["generate"],
            deterministic=True,
        )

    def execute(self, **kwargs):
        return kwargs.get("sum", kwargs.get("a", 0)) + kwargs.get("b", 0)


def test_executor_honors_dependencies():
    registry = ToolRegistry()
    registry.register(_AddTool())
    sandbox = Sandbox()
    graph = TaskGraph(
        [
            TaskNode("one", "", "adder", args={"a": 1, "b": 2}, produces=["sum"]),
            TaskNode("two", "", "adder", args={"a": 0, "b": 0}, requires=["sum"], produces=["double"], parallelizable=True),
        ]
    )

    executor = TopologicalExecutor(registry, sandbox)
    trace = executor.execute(graph)

    assert trace.batches[0] == ["one"]
    assert any(res.output == 3 for res in trace.results if res.node.id == "one")
    assert any(res.output == 3 for res in trace.results if res.node.id == "two")
