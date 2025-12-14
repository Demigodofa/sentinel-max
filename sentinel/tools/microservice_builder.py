"""Generate and manage small FastAPI microservices safely."""
from __future__ import annotations

import os
import threading
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType, ModuleType
from typing import Any, Dict, List, Optional

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
        self._services: Dict[str, "_ServiceProcess"] = {}
        self._last_service: str | None = None
        self.schema = ToolSchema(
            name="microservice_builder",
            version="1.0.0",
            description="Generate sandboxed FastAPI microservices",
            input_schema={
                "description": {"type": "string", "required": False},
                "service_name": {"type": "string", "required": False},
                "port": {"type": "number", "required": False},
                "auto_start": {"type": "boolean", "required": False},
                "action": {"type": "string", "required": False},
                "limit": {"type": "number", "required": False},
            },
            output_schema={
                "type": "object",
                "properties": {
                    "code": "string",
                    "endpoints": "array",
                    "status": "string",
                    "service_name": "string",
                    "code_path": "string",
                    "requirements_path": "string",
                    "run_command": "string",
                    "port": "number",
                    "services": "array",
                    "logs": "array",
                },
            },
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

    def _service_dir(self, service_name: str) -> Path:
        storage_root = os.environ.get("SENTINEL_PROJECT_STORAGE") or "projects"
        path = Path(storage_root).expanduser().resolve() / service_name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _write_files(self, service_name: str, code: str) -> tuple[Path, Path]:
        service_dir = self._service_dir(service_name)
        code_path = service_dir / "app.py"
        requirements_path = service_dir / "requirements.txt"
        code_path.write_text(code, encoding="utf-8")
        requirements = ["fastapi>=0.100.0", "uvicorn>=0.22.0"]
        requirements_path.write_text("\n".join(requirements) + "\n", encoding="utf-8")
        return code_path, requirements_path

    def _record_log(self, process: "_ServiceProcess", message: str) -> None:
        timestamp = datetime.now(UTC).isoformat()
        process.logs.append(f"[{timestamp}] {message}")
        process.logs = process.logs[-200:]

    def _start_service(self, process: "_ServiceProcess", port: int) -> None:
        if uvicorn is None or FastAPI is None:
            raise RuntimeError("FastAPI or uvicorn is unavailable in this environment")

        for existing in self._services.values():
            if (
                existing.name != process.name
                and existing.status == "running"
                and existing.port == port
            ):
                raise RuntimeError(f"Port {port} is already in use by {existing.name}")

        if process.thread and process.thread.is_alive():
            return

        config = uvicorn.Config(process.app, host="0.0.0.0", port=port, log_level="warning")
        server = uvicorn.Server(config)
        process.server = server
        process.port = port

        def _run():  # pragma: no cover - runtime helper
            server.run()

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        process.thread = thread
        process.status = "running"
        self._record_log(process, f"service '{process.name}' started on port {port}")

    def _stop_service(self, process: "_ServiceProcess") -> None:
        if process.server is not None:
            process.server.should_exit = True
        if process.thread and process.thread.is_alive():
            process.thread.join(timeout=2.0)
        process.thread = None
        process.server = None
        process.status = "stopped"
        self._record_log(process, f"service '{process.name}' stopped")

    def _find_service(self, service_name: str | None, port: Optional[int]) -> "_ServiceProcess":
        if service_name and service_name in self._services:
            return self._services[service_name]
        if port is not None:
            for process in self._services.values():
                if process.port == port:
                    return process
        if self._last_service and self._last_service in self._services:
            return self._services[self._last_service]
        raise RuntimeError("No matching microservice is available")

    def _summaries(self) -> List[Dict[str, Any]]:
        summaries = []
        for process in self._services.values():
            summaries.append(
                {
                    "service_name": process.name,
                    "port": process.port,
                    "status": process.status,
                    "code_path": str(process.code_path),
                    "requirements_path": str(process.requirements_path),
                }
            )
        return summaries

    def execute(
        self,
        description: str | List[Dict[str, Any]] | None = None,
        port: int = 8000,
        auto_start: bool = False,
        action: str = "create",
        service_name: str | None = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        normalized_name = (service_name or "microservice").strip() or "microservice"
        action = (action or "create").lower()

        if action == "list":
            return {"status": "ok", "services": self._summaries()}

        if action in {"stop", "restart", "logs"}:
            process = self._find_service(normalized_name, port)
            if action == "stop":
                self._stop_service(process)
                return {"status": process.status, "service_name": process.name, "port": process.port}
            if action == "restart":
                self._stop_service(process)
                self._start_service(process, process.port)
                return {"status": process.status, "service_name": process.name, "port": process.port}
            try:
                limit_count = max(int(limit), 0)
            except (TypeError, ValueError):
                limit_count = 50
            return {
                "status": process.status,
                "service_name": process.name,
                "logs": process.logs[-limit_count:],
            }

        if description is None:
            raise ValueError("description is required when creating a microservice")

        endpoints = self._parse_description(description)
        code = self._render_code(endpoints)
        self._audit(code)
        app = self._sandbox_execute(code)
        code_path, requirements_path = self._write_files(normalized_name, code)
        run_command = f"cd {code_path.parent} && uvicorn app:app --host 0.0.0.0 --port {port}"

        process = _ServiceProcess(
            name=normalized_name,
            app=app,
            endpoints=endpoints,
            code=code,
            code_path=code_path,
            requirements_path=requirements_path,
            run_command=run_command,
            port=port,
        )
        self._services[normalized_name] = process
        self._last_service = normalized_name
        result: Dict[str, Any] = {
            "code": code,
            "endpoints": endpoints,
            "status": process.status,
            "service_name": normalized_name,
            "code_path": str(code_path),
            "requirements_path": str(requirements_path),
            "run_command": run_command,
            "port": port,
        }
        if auto_start:
            try:
                self._start_service(process, port)
                result["status"] = process.status
            except Exception as exc:
                process.status = f"error: {exc}"
                self._record_log(process, f"failed to start: {exc}")
                result["status"] = process.status  # pragma: no cover - runtime guard
        return result

    def start(self, port: int = 8000, service_name: str | None = None) -> None:
        process = self._find_service(service_name, port)
        self._start_service(process, port)

    def stop(self, service_name: str | None = None, port: Optional[int] = None) -> None:
        process = self._find_service(service_name, port)
        self._stop_service(process)


@dataclass
class _ServiceProcess:
    name: str
    app: Any
    endpoints: List[Dict[str, Any]]
    code: str
    code_path: Path
    requirements_path: Path
    run_command: str
    port: int
    status: str = "ready"
    server: Any | None = None
    thread: threading.Thread | None = None
    logs: List[str] = field(default_factory=list)


MICROSERVICE_BUILDER_TOOL = MicroserviceBuilder()
