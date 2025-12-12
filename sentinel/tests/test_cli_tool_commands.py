import pytest

from sentinel.agent_core.base import Tool
from sentinel.controller import SentinelController
from sentinel.tools.tool_schema import ToolSchema


class FakeEchoTool(Tool):
    def __init__(self):
        super().__init__(name="fake", description="Fake echo tool")
        self.schema = ToolSchema(
            name="fake",
            version="0.0.1",
            description="Fake tool for CLI testing",
            input_schema={"x": {"type": "integer"}},
            output_schema={"type": "object"},
            permissions=["test"],
            deterministic=True,
        )

    def execute(self, **kwargs):
        return {"received": kwargs.get("x")}


def test_cli_direct_tool_invocation():
    controller = SentinelController()
    controller.tool_registry.register(FakeEchoTool())

    response = controller.process_input('/tool fake {"x":1}')

    assert response == "{'received': 1}"
