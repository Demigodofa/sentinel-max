"""Advanced tool generator capable of multi-method creation."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

from sentinel.agent_core.base import Tool
from sentinel.agent_core.patch_auditor import PatchAuditor, PatchProposal
from sentinel.tools.registry import DEFAULT_TOOL_REGISTRY, ToolRegistry
from sentinel.tools.tool_generator import SAFE_BUILTINS, _audit_ast


@dataclass
class GeneratedMethodSpec:
    name: str
    description: str
    logic: str


def _parse_spec(spec: str) -> List[GeneratedMethodSpec]:
    """Parse a high level spec into concrete method definitions."""

    try:
        raw = json.loads(spec)
        if isinstance(raw, dict):
            raw = [raw]
        specs: Iterable[Dict[str, Any]] = raw if isinstance(raw, list) else []
    except json.JSONDecodeError:
        # Fallback heuristic: create a single tool that echoes the spec
        specs = [
            {
                "name": "spec_echo",
                "description": spec.strip(),
                "logic": "return description",
            }
        ]

    parsed: List[GeneratedMethodSpec] = []
    for item in specs:
        name = str(item.get("name", "generated_tool"))
        description = str(item.get("description", "Generated tool"))
        logic = str(item.get("logic", "return description"))
        parsed.append(GeneratedMethodSpec(name=name, description=description, logic=logic))
    return parsed


def _build_logic_callable(logic: str):
    tree = _audit_ast(logic)
    compiled = compile(tree, "<advanced-tool>", "exec")

    def _callable(params: Dict[str, Any]) -> Any:
        local_env: Dict[str, Any] = dict(params)
        exec(compiled, {"__builtins__": SAFE_BUILTINS}, local_env)
        return local_env.get("result") or local_env.get("output") or local_env.get("return")

    return _callable


class GeneratedMultiTool(Tool):
    def __init__(
        self, name: str, description: str, logic: str, registry: ToolRegistry | None = None
    ) -> None:
        super().__init__(name, description)
        self._callable = _build_logic_callable(logic)
        self._source = logic
        if registry is not None:
            registry.register(self)

    def execute(self, **kwargs: Any) -> Any:
        return self._callable(kwargs)

    @property
    def source(self) -> str:
        return self._source


def generate_tools_from_spec(
    spec: str, registry: ToolRegistry | None = None, auditor: PatchAuditor | None = None
) -> List[Tool]:
    """Generate multiple tools from a specification string.

    Each generated tool is audited for safety using :class:`PatchAuditor` and
    validated with the same AST guards used by the simple tool generator.
    """

    registry = registry or DEFAULT_TOOL_REGISTRY
    auditor = auditor or PatchAuditor()
    method_specs = _parse_spec(spec)
    generated: List[Tool] = []

    for method in method_specs:
        proposal = PatchProposal(
            target_file=f"generated::{method.name}",
            patch_text=method.logic,
            rationale=f"Generated tool for {method.description}",
        )
        auditor.audit(proposal)
        tool = GeneratedMultiTool(
            name=method.name,
            description=method.description,
            logic=method.logic,
            registry=None,
        )
        registry.register(tool)
        generated.append(tool)
    return generated
