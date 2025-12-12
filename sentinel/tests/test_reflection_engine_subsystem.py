from sentinel.agent_core.base import ExecutionResult, ExecutionTrace
from sentinel.planning.task_graph import TaskNode
from sentinel.reflection.reflection_engine import ReflectionEngine
from sentinel.policy.policy_engine import PolicyEngine
from sentinel.memory.memory_manager import MemoryManager


def test_reflection_engine_flags_failures(tmp_path):
    memory = MemoryManager(storage_dir=tmp_path)
    engine = ReflectionEngine(memory, policy_engine=PolicyEngine())
    trace = ExecutionTrace(
        results=[ExecutionResult(TaskNode("t1", "", None), success=False, error="boom")]
    )

    reflection = engine.reflect(trace, goal="demo")

    assert "execution_failures" in reflection["issues_detected"]
    assert reflection.get("policy_advice") is not None
