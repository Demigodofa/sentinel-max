import json

from sentinel.memory.memory_manager import MemoryManager
from sentinel.orchestration.orchestrator import Orchestrator
from sentinel.tools.registry import ToolRegistry
from sentinel.tools.tool_generator import generate_echo_tool


class FakeLLM:
    def __init__(self):
        self.invocations = 0

    def chat_with_tools(self, messages, tools):
        self.invocations += 1
        if self.invocations == 1:
            return {
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "echo",
                            "arguments": json.dumps({"message": "hello"}),
                        },
                    }
                ],
                "content": "",
            }
        return {"content": "all done"}


def test_plan_updates_are_persisted(tmp_path):
    memory = MemoryManager(storage_dir=tmp_path)
    registry = ToolRegistry()
    generate_echo_tool(prefix="", registry=registry)
    orchestrator = Orchestrator(FakeLLM(), registry, memory)

    result = orchestrator.run("list tools")

    assert "all done" in result
    plans = memory.recall_recent(namespace="plans", limit=1)
    assert plans
    steps = plans[0]["value"].get("steps", [])
    statuses = {step.get("status") for step in steps}
    assert "done" in statuses
    assert any(step.get("tool_name") == "echo" for step in steps)
