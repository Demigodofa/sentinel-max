import pytest

import pytest

from sentinel.policy.policy_engine import PolicyEngine
from sentinel.planning.task_graph import TaskGraph, TaskNode
from sentinel.tools.registry import ToolRegistry
from sentinel.tools.tool_schema import ToolSchema
from sentinel.agent_core.base import Tool


class _DummyTool(Tool):
    def __init__(self, name: str, deterministic: bool) -> None:
        super().__init__(name, deterministic=deterministic)
        self.schema = ToolSchema(
            name=name,
            version="1.0.0",
            description="dummy",
            input_schema={},
            output_schema={},
            permissions=["read"],
            deterministic=deterministic,
        )

    def execute(self, **kwargs):
        return {"echo": kwargs}


def test_policy_enforces_metadata_and_parallel_limits():
    registry = ToolRegistry()
    registry.register(_DummyTool("nondet", deterministic=False))
    nodes = [
        TaskNode("a", "", "nondet", produces=["x"], parallelizable=True),
        TaskNode("b", "", "nondet", produces=["y"], parallelizable=True),
    ]
    graph = TaskGraph(nodes)
    engine = PolicyEngine(parallel_limit=1, deterministic_first=False)

    result = engine.evaluate_plan(graph, registry, enforce=False)

    assert all(not node.parallelizable for node in graph)
    assert result.allowed
    assert "Parallel limit exceeded" in " ".join(result.rewrites)


def test_policy_detects_artifact_collisions():
    registry = ToolRegistry()
    registry.register(_DummyTool("safe", deterministic=True))
    graph = TaskGraph(
        [
            TaskNode("one", "", "safe", produces=["artifact"]),
            TaskNode("two", "", "safe", produces=["artifact"]),
        ]
    )
    engine = PolicyEngine()

    result = engine.evaluate_plan(graph, registry, enforce=False)
    assert not result.allowed
    assert any("Artifact collision" in reason for reason in result.reasons)
    with pytest.raises(PermissionError):
        engine.evaluate_plan(graph, registry)
