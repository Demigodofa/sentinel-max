"""Generate small FastAPI microservices safely."""
from __future__ import annotations

import threading
import sys
from types import MappingProxyType, ModuleType
from typing import Any, Dict, List

try:  # Optional dependency
    import uvicorn  # type: ignore
except Exception:  # pragma: no cover
    uvicorn = None

try:  # Optional dependency
    from fastapi import FastAPI  # type: ignore
except Exception:  # pragma: no cover
    FastAPI = None

from sentinel.agent_core.base import Tool
from sentinel.agent_core.patch_auditor import PatchAuditor, PatchProposal
from sentinel.logging.logger import get_logger
from sentinel.tools.tool_schema import ToolSchema

logger = get_logger(__name__)

SAFE_BUILTINS = MappingProxyType({
    "__builtins__": {
        "len": len,
        "sum": sum,
        "min": min,
        "max": max,
        "__import__": __import__,
    }
})


def _ensure_fastapi() -> Any:
    if FastAPI is not None:
        return FastAPI

    class _StubApp(dict):
        def __init__(self) -> None:
            super().__init__()
            self.routes: List[Dict[str, Any]] = []

        def get(self, path: str):  # type: ignore[override]
            def decorator(func):
                self.routes.append({"method": "GET", "path": path, "func": func})
                return func

            return decorator

        def post(self, path: str):  # type: ignore[override]
            def decorator(func):
                self.routes.append({"method": "POST", "path": path, "func": func})
                return func

            return decorator

    return _StubApp


class MicroserviceBuilder(Tool):
    def __init__(self, auditor: PatchAuditor | None = None) -> None:
        super().__init__(
            "microservice_builder",
            "Generate sandboxed FastAPI microservices",
            deterministic=False,
        )
        self.auditor = auditor or PatchAuditor()
        self._app = None
        self._server_thread: threading.Thread | None = None
        self._uvicorn_server = None
        self.schema = ToolSchema(
            name="microservice_builder",
            version="1.0.0",
            description="Generate sandboxed FastAPI microservices",
            input_schema={"description": {"type": "string", "required": True}, "port": {"type": "number", "required": False}, "auto_start": {"type": "boolean", "required": False}},
            output_schema={"type": "object", "properties": {"code": "string", "endpoints": "array", "status": "string"}},
            permissions=["fs:read-limited", "net:listen"],
            deterministic=False,
        )

    def _render_code(self, endpoints: List[Dict[str, Any]]) -> str:
        lines: List[str] = [
            "from fastapi import FastAPI",
            "",
            "app = FastAPI()",
            "get = app.get",
            "post = app.post",
            "",
        ]
        for endpoint in endpoints:
            path = endpoint.get("path", "/ping")
            method = endpoint.get("method", "get").lower()
            response = endpoint.get("response", {"message": "ok"})
            func_name = f"endpoint_{method}_{abs(hash(path)) % 10_000}"
            lines.append(f"@{method}(\"{path}\")")
            lines.append(f"async def {func_name}():")
            lines.append(f"    return {response!r}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def _sandbox_execute(self, code: str) -> Any:
        namespace: Dict[str, Any] = dict(SAFE_BUILTINS)
        namespace["FastAPI"] = _ensure_fastapi()
        restore_fastapi: tuple[str, ModuleType | None] | None = None
        if FastAPI is None:
            stub_module = ModuleType("fastapi")
            stub_module.FastAPI = namespace["FastAPI"]  # type: ignore[attr-defined]
            restore_fastapi = ("fastapi", sys.modules.get("fastapi"))
            sys.modules["fastapi"] = stub_module
        try:
            exec(code, namespace, namespace)
            return namespace.get("app")
        finally:
            if restore_fastapi:
                name, original = restore_fastapi
                if original is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = original

    def _audit(self, code: str) -> None:
        proposal = PatchProposal(target_file="generated_microservice.py", patch_text=code, rationale="auto")
        self.auditor.audit(proposal)

    def _parse_description(self, description: str | List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if isinstance(description, list):
            return description
        endpoints: List[Dict[str, Any]] = []
        for line in description.splitlines():
            if not line.strip():
                continue
            parts = [p.strip() for p in line.split("-") if p.strip()]
            path = parts[0] if parts else "/ping"
            response = {"message": parts[1]} if len(parts) > 1 else {"message": "ok"}
            endpoints.append({"path": path, "method": "get", "response": response})
        if not endpoints:
            endpoints.append({"path": "/ping", "method": "get", "response": {"message": "pong"}})
        return endpoints

    def execute(self, description: str | List[Dict[str, Any]], port: int = 8000, auto_start: bool = False) -> Dict[str, Any]:
        endpoints = self._parse_description(description)
        code = self._render_code(endpoints)
        self._audit(code)
        app = self._sandbox_execute(code)
        self._app = app
        result: Dict[str, Any] = {"code": code, "endpoints": endpoints, "status": "ready"}
        if auto_start:
            try:
                self.start(port=port)
                result["status"] = "running"
                result["port"] = port
            except Exception as exc:
                result["status"] = f"error: {exc}"  # pragma: no cover - runtime guard
        return result

    def start(self, port: int = 8000) -> None:
        if self._app is None:
            raise RuntimeError("No microservice has been generated yet")
        if uvicorn is None or FastAPI is None:
            raise RuntimeError("FastAPI or uvicorn is unavailable in this environment")
        if self._server_thread and self._server_thread.is_alive():
            return

        config = uvicorn.Config(self._app, host="0.0.0.0", port=port, log_level="warning")
        server = uvicorn.Server(config)
        self._uvicorn_server = server

        def _run():  # pragma: no cover - runtime helper
            server.run()

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        self._server_thread = thread

    def stop(self) -> None:
        if self._uvicorn_server is not None:
            self._uvicorn_server.should_exit = True
        if self._server_thread and self._server_thread.is_alive():
            self._server_thread.join(timeout=2.0)
        self._server_thread = None
        self._uvicorn_server = None


MICROSERVICE_BUILDER_TOOL = MicroserviceBuilder()
