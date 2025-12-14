import json

import pytest

from sentinel.agent_core.sandbox import Sandbox
from sentinel.llm.orchestrator import ToolCallingOrchestrator
from sentinel.memory.memory_manager import MemoryManager
from sentinel.tools.filesystem_tools import FSListTool
from sentinel.tools.registry import ToolRegistry


class StubLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def supports_tool_calls(self):
        return True

    def chat_with_tools(self, messages, tools, **kwargs):
        self.calls.append({"messages": messages, "tools": tools})
        if not self.responses:
            return {"content": "", "tool_calls": []}
        return self.responses.pop(0)


class DisabledLLM:
    def supports_tool_calls(self):
        return False


@pytest.fixture
def sandbox_registry(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTINEL_SANDBOX_ROOT", str(tmp_path))
    registry = ToolRegistry()
    registry.register(FSListTool())
    return registry


def test_seeded_action_executes_tools(monkeypatch, tmp_path, sandbox_registry):
    llm = StubLLM(responses=[{"content": "listing complete", "tool_calls": []}])
    sandbox = Sandbox()
    memory = MemoryManager()
    orchestrator = ToolCallingOrchestrator(llm, sandbox_registry, sandbox, memory=memory)

    result = orchestrator.handle("action: fs_list {\"path\": \".\"}")

    assert result["trace"]
    assert any(entry["tool"] == "fs_list" for entry in result["trace"])
    assert llm.calls  # LLM still queried for summary
    execution_records = memory.recall_recent(namespace="execution_real")
    assert execution_records


def test_llm_selected_tool_runs(monkeypatch, tmp_path, sandbox_registry):
    llm = StubLLM(
        responses=[
            {
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "fs_list", "arguments": json.dumps({"path": "."})},
                    }
                ],
            },
            {"content": "done", "tool_calls": []},
        ]
    )
    sandbox = Sandbox()
    memory = MemoryManager()
    orchestrator = ToolCallingOrchestrator(llm, sandbox_registry, sandbox, memory=memory)

    result = orchestrator.handle("list files in sandbox")

    assert any(entry["tool"] == "fs_list" for entry in result["trace"])
    assert "done" in result["response"]


def test_backend_without_tool_calls(monkeypatch, tmp_path, sandbox_registry):
    sandbox = Sandbox()
    memory = MemoryManager()
    orchestrator = ToolCallingOrchestrator(DisabledLLM(), sandbox_registry, sandbox, memory=memory)

    result = orchestrator.handle("list files")

    assert "unavailable" in result["response"].lower()
