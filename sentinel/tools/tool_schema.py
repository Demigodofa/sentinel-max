"""Tool metadata schemas and validation utilities."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, List

from sentinel.agent_core.base import Tool

SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


@dataclass
class ToolSchema:
    """Declarative metadata describing a tool's contract."""

    name: str
    version: str
    description: str
    input_schema: Dict[str, Dict[str, Any]]
    output_schema: Dict[str, Any]
    permissions: List[str]
    deterministic: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolSchema":
        return cls(**data)


class ToolValidator:
    """Validate :class:`Tool` instances against :class:`ToolSchema`."""

    forbidden_builtins = {"exec", "eval", "__import__", "open"}

    @classmethod
    def validate(cls, tool: Tool, schema: ToolSchema) -> None:
        cls._validate_schema(schema)
        cls._validate_tool(tool, schema)
        cls._validate_permissions(schema)
        cls._validate_determinism(tool, schema)
        cls._check_forbidden_builtins(tool)

    @classmethod
    def _validate_schema(cls, schema: ToolSchema) -> None:
        if not schema.name:
            raise ValueError("Tool schema must include a name")
        if not SEMVER_PATTERN.match(schema.version):
            raise ValueError(f"Tool schema for {schema.name} must use semver version")
        if not schema.description:
            raise ValueError(f"Tool schema for {schema.name} missing description")
        if not isinstance(schema.input_schema, dict) or not isinstance(schema.output_schema, dict):
            raise TypeError("Tool schema input/output schemas must be dictionaries")
        if not isinstance(schema.permissions, list) or not all(
            isinstance(p, str) for p in schema.permissions
        ):
            raise TypeError("Tool schema permissions must be list[str]")

    @classmethod
    def _validate_tool(cls, tool: Tool, schema: ToolSchema) -> None:
        if not isinstance(tool, Tool):
            raise TypeError("Registered object must be a Tool instance")
        if tool.name != schema.name:
            raise ValueError(
                f"Tool schema name {schema.name} does not match tool name {tool.name}"
            )

    @classmethod
    def _validate_permissions(cls, schema: ToolSchema) -> None:
        if not schema.permissions:
            raise ValueError(f"Tool {schema.name} must declare permissions")

    @classmethod
    def _validate_determinism(cls, tool: Tool, schema: ToolSchema) -> None:
        deterministic_flag = getattr(tool, "deterministic", True)
        if deterministic_flag != schema.deterministic:
            raise ValueError(
                f"Determinism flag mismatch for {schema.name}: tool={deterministic_flag} schema={schema.deterministic}"
            )

    @classmethod
    def _check_forbidden_builtins(cls, tool: Tool) -> None:
        names = set(getattr(tool.execute, "__code__", None).co_names) if hasattr(tool, "execute") else set()
        dangerous = names.intersection(cls.forbidden_builtins)
        if dangerous:
            raise ValueError(
                f"Tool {tool.name} references forbidden builtins: {', '.join(sorted(dangerous))}"
            )

