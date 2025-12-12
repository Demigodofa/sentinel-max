from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from sentinel.agent_core.base import Tool
from sentinel.config.sandbox_config import ensure_sandbox_root_exists
from sentinel.logging.logger import get_logger
from sentinel.tools.tool_schema import ToolSchema

logger = get_logger(__name__)


def _resolve_in_sandbox(path: str) -> Path:
    root = ensure_sandbox_root_exists().resolve()
    target = Path(path).expanduser()
    if not target.is_absolute():
        target = root / target
    target = target.resolve()
    if root != target and root not in target.parents:
        raise PermissionError(f"Refusing path outside sandbox: {target} (root={root})")
    return target


@dataclass
class FSListTool(Tool):
    name: str = "fs_list"
    description: str = "List files/folders under the sandbox root."
    permissions: tuple[str, ...] = ("fs:read",)

    def __post_init__(self) -> None:
        super().__init__(self.name, self.description, deterministic=True)
        self.schema = ToolSchema(
            name=self.name,
            version="1.0.0",
            description=self.description,
            input_schema={
                "path": {"type": "string", "required": False},
                "recursive": {"type": "boolean", "required": False},
                "max_items": {"type": "integer", "required": False},
            },
            output_schema={"type": "object"},
            permissions=list(self.permissions),
            deterministic=True,
        )

    def execute(self, path: str = ".", recursive: bool = False, max_items: int = 200) -> Dict[str, Any]:
        return self.run(path=path, recursive=recursive, max_items=max_items)

    def run(self, path: str = ".", recursive: bool = False, max_items: int = 200) -> Dict[str, Any]:
        p = _resolve_in_sandbox(path)
        if not p.exists():
            return {"ok": False, "error": "path_not_found", "path": str(p)}
        items = []
        iterator = p.rglob("*") if recursive else p.iterdir()
        for i, child in enumerate(iterator):
            if i >= max_items:
                break
            items.append(
                {
                    "path": str(child),
                    "is_dir": child.is_dir(),
                    "size": child.stat().st_size if child.is_file() else None,
                }
            )
        return {"ok": True, "path": str(p), "items": items}


@dataclass
class FSReadTool(Tool):
    name: str = "fs_read"
    description: str = "Read a text file inside the sandbox root."
    permissions: tuple[str, ...] = ("fs:read",)

    def __post_init__(self) -> None:
        super().__init__(self.name, self.description, deterministic=True)
        self.schema = ToolSchema(
            name=self.name,
            version="1.0.0",
            description=self.description,
            input_schema={"path": {"type": "string", "required": True}, "max_bytes": {"type": "integer", "required": False}},
            output_schema={"type": "object"},
            permissions=list(self.permissions),
            deterministic=True,
        )

    def execute(self, path: str, max_bytes: int = 200_000) -> Dict[str, Any]:
        return self.run(path=path, max_bytes=max_bytes)

    def run(self, path: str, max_bytes: int = 200_000) -> Dict[str, Any]:
        p = _resolve_in_sandbox(path)
        if not p.exists() or not p.is_file():
            return {"ok": False, "error": "file_not_found", "path": str(p)}
        data = p.read_bytes()
        truncated = False
        if len(data) > max_bytes:
            data = data[:max_bytes]
            truncated = True
        try:
            text = data.decode("utf-8", errors="replace")
        except Exception:
            text = data.decode(errors="replace")
        return {"ok": True, "path": str(p), "truncated": truncated, "text": text}


@dataclass
class FSWriteTool(Tool):
    name: str = "fs_write"
    description: str = "Write/overwrite a text file inside the sandbox root."
    permissions: tuple[str, ...] = ("fs:write",)

    def __post_init__(self) -> None:
        super().__init__(self.name, self.description, deterministic=True)
        self.schema = ToolSchema(
            name=self.name,
            version="1.0.0",
            description=self.description,
            input_schema={
                "path": {"type": "string", "required": True},
                "text": {"type": "string", "required": True},
                "mkdirs": {"type": "boolean", "required": False},
            },
            output_schema={"type": "object"},
            permissions=list(self.permissions),
            deterministic=True,
        )

    def execute(self, path: str, text: str, mkdirs: bool = True) -> Dict[str, Any]:
        return self.run(path=path, text=text, mkdirs=mkdirs)

    def run(self, path: str, text: str, mkdirs: bool = True) -> Dict[str, Any]:
        p = _resolve_in_sandbox(path)
        if mkdirs:
            p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", errors="replace")
        return {"ok": True, "path": str(p), "bytes": p.stat().st_size}


@dataclass
class FSDeleteTool(Tool):
    name: str = "fs_delete"
    description: str = "Delete a file/folder inside the sandbox root (guarded)."
    permissions: tuple[str, ...] = ("fs:delete",)

    def __post_init__(self) -> None:
        super().__init__(self.name, self.description, deterministic=True)
        self.schema = ToolSchema(
            name=self.name,
            version="1.0.0",
            description=self.description,
            input_schema={"path": {"type": "string", "required": True}, "recursive": {"type": "boolean", "required": False}},
            output_schema={"type": "object"},
            permissions=list(self.permissions),
            deterministic=True,
        )

    def execute(self, path: str, recursive: bool = False) -> Dict[str, Any]:
        return self.run(path=path, recursive=recursive)

    def run(self, path: str, recursive: bool = False) -> Dict[str, Any]:
        p = _resolve_in_sandbox(path)
        root = ensure_sandbox_root_exists().resolve()
        if p == root:
            return {"ok": False, "error": "refuse_delete_root", "path": str(p)}
        if not p.exists():
            return {"ok": False, "error": "path_not_found", "path": str(p)}
        if p.is_dir():
            if not recursive:
                return {"ok": False, "error": "dir_requires_recursive_true", "path": str(p)}
            for child in sorted(p.rglob("*"), reverse=True):
                if child.is_file():
                    child.unlink(missing_ok=True)
                else:
                    child.rmdir()
            p.rmdir()
            return {"ok": True, "deleted": str(p), "recursive": True}
        p.unlink(missing_ok=True)
        return {"ok": True, "deleted": str(p), "recursive": False}
