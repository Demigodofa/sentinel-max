"""Generate sandbox-friendly tools dynamically."""
from __future__ import annotations

import ast
from types import MappingProxyType
from typing import Any, Callable, Dict, Optional

from sentinel.agent_core.base import Tool
from sentinel.tools.registry import DEFAULT_TOOL_REGISTRY, ToolRegistry
from sentinel.tools.tool_schema import ToolSchema


SAFE_BUILTINS = MappingProxyType(
    {
        "len": len,
        "min": min,
        "max": max,
        "sum": sum,
        "all": all,
        "any": any,
        "sorted": sorted,
        "range": range,
        "enumerate": enumerate,
        "zip": zip,
        "abs": abs,
        "round": round,
    }
)


def _audit_ast(snippet: str) -> ast.AST:
    tree = ast.parse(snippet, mode="exec")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise ValueError("Imports are not allowed in generated tools")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"exec", "eval", "open", "__import__"}:
                raise ValueError(f"Dangerous call detected: {node.func.id}")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise ValueError("Access to dunder attributes is not allowed")
    return tree


def _build_callable(snippet: str) -> Callable[[Dict[str, Any]], Any]:
    tree = _audit_ast(snippet)
    try:
        expression = ast.Expression(tree.body[0].value)  # type: ignore[index]
        code_obj = compile(expression, "<generated-tool>", "eval")

        def _callable(params: Dict[str, Any]) -> Any:
            return eval(code_obj, {"__builtins__": SAFE_BUILTINS}, params)

        return _callable
    except Exception:
        compiled = compile(tree, "<generated-tool>", "exec")

        def _callable(params: Dict[str, Any]) -> Any:
            local_env: Dict[str, Any] = dict(params)
            exec(compiled, {"__builtins__": SAFE_BUILTINS}, local_env)
            return local_env.get("result")

        return _callable


class GeneratedTool(Tool):
    def __init__(
        self,
        name: str,
        description: str,
        snippet: str,
        registry: Optional[ToolRegistry] = None,
    ) -> None:
        super().__init__(name=name, description=description, deterministic=True)
        self._snippet = snippet
        self._callable = _build_callable(snippet)
        self.schema = ToolSchema(
            name=name,
            version="1.0.0",
            description=description,
            input_schema={"*": {"type": "object", "required": False}},
            output_schema={"type": "any"},
            permissions=["compute"],
            deterministic=True,
        )
        if registry is not None:
            registry.register(self)

    def execute(self, **kwargs: Any) -> Any:
        return self._callable(kwargs)


def generate_echo_tool(prefix: str = "", registry: ToolRegistry | None = None) -> Tool:
    """Return a deterministic echo tool."""

    class EchoTool(Tool):
        def __init__(self) -> None:
            super().__init__("echo", "Simple echo helper", deterministic=True)
            self.schema = ToolSchema(
                name="echo",
                version="1.0.0",
                description="Simple echo helper",
                input_schema={"message": {"type": "string", "required": True}},
                output_schema={"type": "string"},
                permissions=["compute"],
                deterministic=True,
            )

        def execute(self, message: str, **_: Any) -> str:
            return f"{prefix}{message}"

    tool = EchoTool()
    if registry is None:
        registry = DEFAULT_TOOL_REGISTRY
    if registry.has_tool(tool.name):
        return registry.get(tool.name)
    registry.register(tool)
    return tool


def generate_custom_tool(
    name: str,
    description: str,
    code_snippet: str,
    registry: Optional[ToolRegistry] = None,
) -> Tool:
    """Generate a tool from a natural language description and Python snippet."""

    registry = registry or DEFAULT_TOOL_REGISTRY
    tool = GeneratedTool(name=name, description=description, snippet=code_snippet, registry=None)
    registry.register(tool)
    return tool
