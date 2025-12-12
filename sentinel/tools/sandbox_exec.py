from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Any, Dict, List

from sentinel.agent_core.base import Tool
from sentinel.config.sandbox_config import ensure_sandbox_root_exists
from sentinel.tools.tool_schema import ToolSchema


@dataclass
class SandboxExecTool(Tool):
    name: str = "sandbox_exec"
    description: str = "Run a command ONLY with cwd set to the sandbox root."
    permissions: tuple[str, ...] = ("exec:sandbox",)

    def __post_init__(self) -> None:
        super().__init__(self.name, self.description, deterministic=False)
        self.schema = ToolSchema(
            name=self.name,
            version="1.0.0",
            description=self.description,
            input_schema={"argv": {"type": "array", "items": "string", "required": True}, "timeout_s": {"type": "integer", "required": False}},
            output_schema={"type": "object"},
            permissions=list(self.permissions),
            deterministic=False,
        )

    def execute(self, argv: List[str], timeout_s: int = 60) -> Dict[str, Any]:
        return self.run(argv=argv, timeout_s=timeout_s)

    def run(self, argv: List[str], timeout_s: int = 60) -> Dict[str, Any]:
        root = ensure_sandbox_root_exists()
        if not argv:
            return {"ok": False, "error": "empty_command"}
        try:
            cp = subprocess.run(
                argv,
                cwd=str(root),
                timeout=timeout_s,
                capture_output=True,
                text=True,
            )
            return {
                "ok": True,
                "argv": argv,
                "returncode": cp.returncode,
                "stdout": cp.stdout[-20000:],
                "stderr": cp.stderr[-20000:],
            }
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "timeout", "argv": argv, "timeout_s": timeout_s}
