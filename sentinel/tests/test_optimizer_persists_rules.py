from sentinel.memory.memory_manager import MemoryManager
from sentinel.orchestration.optimizer import Optimizer
from sentinel.tools.registry import ToolRegistry


def test_optimizer_writes_alias_and_intent_rules(tmp_path):
    memory = MemoryManager(storage_dir=tmp_path)
    registry = ToolRegistry()
    memory.store_fact("tool_events", key=None, value={"event": "tool_repair", "tool": "demo", "dropped_arg": "unused"})
    optimizer = Optimizer(registry, memory)

    corrections = [{"assumption": "cleanup", "action": "fs_delete", "feedback": "no"}]
    result = optimizer.optimize(corrections=corrections)

    alias_file = memory.base_dir / "tool_aliases.json"
    assert alias_file.exists()
    intent_rules = memory.recall_recent(namespace="intent_rules")
    assert intent_rules
    assert result["alias_rules"] >= 1
    assert result["intent_rules"] >= 1
