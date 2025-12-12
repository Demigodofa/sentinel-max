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
            input_schema={},
            output_schema={},
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
