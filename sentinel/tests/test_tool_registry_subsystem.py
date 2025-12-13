import pytest

from sentinel.agent_core.base import Tool
from sentinel.tools.registry import ToolRegistry
from sentinel.tools.tool_schema import ToolSchema


class _EchoTool(Tool):
    def __init__(self, name="echo"):
        super().__init__(name)
        self.schema = ToolSchema(
            name=name,
            version="1.0.0",
            description="echo",
            input_schema={"text": {"type": "string", "required": False}},
            output_schema={"text": "string"},
            permissions=["read"],
        )

    def execute(self, **kwargs):
        return kwargs


def test_registry_prevents_duplicates():
    registry = ToolRegistry()
    registry.register(_EchoTool())

    with pytest.raises(ValueError):
        registry.register(_EchoTool())


def test_registry_describes_tools():
    registry = ToolRegistry()
    registry.register(_EchoTool("echo2"))

    described = registry.describe_tools()
    assert "echo2" in described and described["echo2"]["name"] == "echo2"


def test_prompt_safe_summary_is_read_only():
    registry = ToolRegistry()
    registry.register(_EchoTool("immutable"))

    summary = registry.prompt_safe_summary()
    summary["immutable"]["permissions"].append("mutated")
    summary["immutable"]["outputs"]["new_field"] = "bad"
    summary["immutable"]["inputs"]["text"]["type"] = "corrupted"

    new_summary = registry.prompt_safe_summary()
    described = registry.describe_tools()

    assert "mutated" not in described["immutable"]["permissions"]
    assert "new_field" not in new_summary["immutable"]["outputs"]
    assert new_summary["immutable"]["inputs"]["text"]["type"] == "string"
