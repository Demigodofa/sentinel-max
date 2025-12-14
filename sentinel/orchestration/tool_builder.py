"""Helper to generate missing tools safely."""
from __future__ import annotations

import importlib
import json
import subprocess
from pathlib import Path
from typing import Dict

from sentinel.agent_core.base import Tool
from sentinel.logging.logger import get_logger
from sentinel.memory.memory_manager import MemoryManager
from sentinel.tools.registry import ToolRegistry

logger = get_logger(__name__)


class ToolBuilder:
    """Build deterministic tools when the orchestrator detects a gap."""

    def __init__(self, tool_registry: ToolRegistry, memory: MemoryManager, docs_path: Path | None = None) -> None:
        self.tool_registry = tool_registry
        self.memory = memory
        self.docs_path = docs_path or Path("AGENTS.md")

    def build_tool(self, tool_name: str, purpose: str, inputs: Dict, outputs: Dict) -> Dict:
        module_path = Path("sentinel/tools") / f"{tool_name}.py"
        class_name = "".join(part.capitalize() for part in tool_name.split("_")) + "Tool"
        input_schema = {key: {"type": meta.get("type", "string"), "description": meta.get("description", ""), "required": bool(meta.get("required", False))} for key, meta in (inputs or {}).items()}
        output_schema = outputs or {"type": "object", "description": "Structured tool output"}
        code = f"""
from __future__ import annotations
from typing import Any, Dict

from sentinel.agent_core.base import Tool
from sentinel.tools.tool_schema import ToolSchema


class {class_name}(Tool):
    def __init__(self) -> None:
        super().__init__("{tool_name}", "{purpose}", deterministic=True)
        self.schema = ToolSchema(
            name="{tool_name}",
            version="1.0.0",
            description="{purpose}",
            input_schema={json.dumps(input_schema, indent=4)},
            output_schema={json.dumps(output_schema, indent=4)},
            permissions=["compute"],
            deterministic=True,
        )

    def execute(self, **kwargs: Any) -> Dict[str, Any]:
        return {{"ok": True, "received": kwargs, "summary": "{purpose}"}}


tool = {class_name}()
"""
        module_path.write_text(code.strip() + "\n", encoding="utf-8")
        logger.info("Wrote generated tool to %s", module_path)

        test_path = Path("sentinel/tests") / f"test_tool_{tool_name}.py"
        test_code = f"""
from sentinel.tools.registry import ToolRegistry
from sentinel.orchestration.tool_builder import ToolBuilder
from sentinel.memory.memory_manager import MemoryManager


def test_generated_tool_executes(tmp_path):
    memory = MemoryManager(storage_dir=tmp_path)
    registry = ToolRegistry()
    builder = ToolBuilder(registry, memory)
    result = builder.build_tool(
        "{tool_name}",
        "{purpose}",
        inputs={json.dumps(inputs or {}, indent=4)},
        outputs={json.dumps(output_schema, indent=4)},
    )
    tool = registry.get("{tool_name}")
    assert tool.execute(example="ok")
    assert result["ok"]
"""
        test_path.write_text(test_code.strip() + "\n", encoding="utf-8")
        logger.info("Wrote generated tool test to %s", test_path)

        self._register_tool(tool_name, class_name)
        self._update_docs(tool_name, purpose)
        self._compile_and_test(tool_name)
        record = {
            "tool": tool_name,
            "purpose": purpose,
            "inputs": inputs,
            "outputs": outputs,
            "module": f"sentinel.tools.{tool_name}",
            "class": class_name,
            "test": f"sentinel/tests/test_tool_{tool_name}.py",
            "ok": True,
        }
        self.memory.store_fact("generated_tools", key=tool_name, value=record)
        return record

    def _register_tool(self, tool_name: str, class_name: str) -> None:
        importlib.invalidate_caches()
        module = importlib.import_module(f"sentinel.tools.{tool_name}")
        tool_obj = getattr(module, "tool", None) or getattr(module, class_name, None)
        if isinstance(tool_obj, type) and issubclass(tool_obj, Tool):
            tool_obj = tool_obj()
        if not isinstance(tool_obj, Tool):
            raise ValueError("Generated module does not expose a Tool")
        if not self.tool_registry.has_tool(tool_name):
            self.tool_registry.register(tool_obj)

    def _compile_and_test(self, tool_name: str) -> None:
        try:
            subprocess.run(["python", "-m", "compileall", "sentinel"], check=True, capture_output=True)
            subprocess.run(["python", "-m", "pytest", "-q", f"sentinel/tests/test_tool_{tool_name}.py"], check=True, capture_output=True)
        except subprocess.CalledProcessError as exc:  # pragma: no cover - defensive
            logger.error("Generated tool validation failed: %s", exc)
            raise

    def _update_docs(self, tool_name: str, purpose: str) -> None:
        path = Path(self.docs_path)
        if not path.exists():
            return
        try:
            existing = path.read_text(encoding="utf-8")
        except Exception:  # pragma: no cover - defensive
            return
        marker = "\n## Generated Tools\n"
        if marker not in existing:
            existing += marker
        if tool_name in existing:
            content = existing
        else:
            content = existing + f"- **{tool_name}**: {purpose}\n"
        path.write_text(content, encoding="utf-8")
