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


def test_web_search_aliases_and_filtering():
    registry = ToolRegistry()
    schema = ToolSchema(
        name="web_search",
        version="1.0.0",
        description="search",
        input_schema={
            "query": {"type": "string", "required": True},
            "max_results": {"type": "integer", "required": False},
        },
        output_schema={"results": "array"},
        permissions=["internet"],
    )

    normalized = registry._normalize_args(
        "web_search",
        {"query": "x", "num_results": "5", "limit": 3, "extra": "ignored"},
        schema,
    )

    assert normalized == {"query": "x", "max_results": 5}


def test_sandbox_exec_alias_and_string_conversion():
    registry = ToolRegistry()
    schema = ToolSchema(
        name="sandbox_exec",
        version="1.0.0",
        description="sandboxed exec",
        input_schema={"argv": {"type": "array", "required": True}},
        output_schema={"result": "string"},
        permissions=["execute"],
    )

    normalized = registry._normalize_args(
        "sandbox_exec", {"command": "python -c 'print(1)'"}, schema
    )

    assert normalized == {"argv": ["python", "-c", "print(1)"]}


def test_microservice_builder_endpoint_alias():
    registry = ToolRegistry()
    schema = ToolSchema(
        name="microservice_builder",
        version="1.0.0",
        description="builder",
        input_schema={
            "description": {"type": "any", "required": True},
            "auto_start": {"type": "boolean", "required": False},
        },
        output_schema={"service_path": "string"},
        permissions=["write"],
    )

    endpoints = [{"path": "/health", "method": "GET", "response": {"ok": True}}]
    normalized = registry._normalize_args(
        "microservice_builder",
        {"endpoints": endpoints, "auto_start": True, "unused": "drop"},
        schema,
    )

    assert normalized == {"description": endpoints, "auto_start": True}
