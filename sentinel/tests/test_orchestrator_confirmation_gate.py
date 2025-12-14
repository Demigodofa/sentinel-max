from sentinel.agent_core.base import Tool
from sentinel.memory.memory_manager import MemoryManager
from sentinel.orchestration.orchestrator import Orchestrator
from sentinel.tools.registry import ToolRegistry
from sentinel.tools.tool_schema import ToolSchema
import json


class FakeDeleteTool(Tool):
    def __init__(self):
        super().__init__("fs_delete", "Delete files safely", deterministic=True)
        self.calls = 0
        self.schema = ToolSchema(
            name="fs_delete",
            version="1.0.0",
            description="Delete files",
            input_schema={"path": {"type": "string", "description": "Path to delete"}},
            output_schema={"type": "object"},
            permissions=["fs"],
            deterministic=True,
        )

    def execute(self, path: str = ""):
        self.calls += 1
        return {"ok": True, "path": path}


class RiskyLLM:
    def chat_with_tools(self, messages, tools):
        return {
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "fs_delete", "arguments": json.dumps({"path": "/tmp/test"})},
                }
            ],
            "content": "",
        }


def test_confirmation_gate_blocks_execution(tmp_path):
    memory = MemoryManager(storage_dir=tmp_path)
    registry = ToolRegistry()
    delete_tool = FakeDeleteTool()
    registry.register(delete_tool)
    orchestrator = Orchestrator(RiskyLLM(), registry, memory)

    prompt = orchestrator.run("remove the temp file")

    assert "Proceed?" in prompt
    assert delete_tool.calls == 0

    follow_up = orchestrator.handle_confirmation("no")
    assert "Why did you assume" in follow_up
    intent_rules = memory.recall_recent(namespace="intent_rules")
    assert intent_rules
    plans = memory.recall_recent(namespace="plans", limit=1)
    assert any(step.get("status") == "failed" for step in plans[0]["value"].get("steps", []))
