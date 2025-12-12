from sentinel.memory.memory_manager import MemoryManager
from sentinel.planning.adaptive_planner import AdaptivePlanner
from sentinel.tools.registry import ToolRegistry
from sentinel.policy.policy_engine import PolicyEngine


def test_adaptive_planner_builds_graph_with_metadata(tmp_path):
    memory = MemoryManager(storage_dir=tmp_path)
    registry = ToolRegistry()
    planner = AdaptivePlanner(registry, memory=memory, policy_engine=PolicyEngine())

    graph = planner.plan("write a small note")

    assert graph.metadata.get("origin_goal") == "write a small note"
    assert graph.metadata.get("reasoning_trace")
