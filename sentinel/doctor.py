"""Sentinel MAX environment health report utility.

Run via ``python -m sentinel.doctor`` to validate imports, storage paths,
intents, and interpreter details.
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4

from sentinel.conversation.intent import Intent, classify_intent


def _find_repo_root(start: Path | None = None) -> Path:
    start_path = start or Path(__file__).resolve()
    for candidate in [start_path, *start_path.parents]:
        if (candidate / ".git").exists():
            return candidate if candidate.is_dir() else candidate.parent
    return Path(__file__).resolve().parent.parent


def _venv_active() -> bool:
    return (
        sys.prefix != getattr(sys, "base_prefix", sys.prefix)
        or sys.prefix != getattr(sys, "real_prefix", sys.prefix)
        or "VIRTUAL_ENV" in os.environ
    )


def _resolve_storage_path(env_var: str, default: Path) -> Path:
    raw = os.environ.get(env_var)
    if raw:
        return Path(os.path.expanduser(raw)).resolve()
    return default.resolve()


def _memory_default_dir() -> Path:
    from sentinel.memory import memory_manager

    return Path(memory_manager.__file__).resolve().parent


def _project_default_dir() -> Path:
    return Path(os.path.expanduser("projects")).resolve()


def _probe_directory(path: Path) -> Dict[str, Any]:
    path.mkdir(parents=True, exist_ok=True)
    probe_file = path / f"doctor_probe_{uuid4().hex}.txt"
    result = {"path": str(path), "write": False, "read": False, "cleanup": True}
    payload = "sentinel doctor"
    try:
        probe_file.write_text(payload, encoding="utf-8")
        result["write"] = True
        result["read"] = probe_file.read_text(encoding="utf-8") == payload
    except Exception as exc:  # pragma: no cover - defensive
        result["error"] = str(exc)
    finally:
        try:
            if probe_file.exists():
                probe_file.unlink()
        except Exception as exc:  # pragma: no cover - defensive
            result["cleanup"] = False
            result["cleanup_error"] = str(exc)
    return result


def _import_check(module_name: str) -> Dict[str, Any]:
    try:
        importlib.import_module(module_name)
        return {"module": module_name, "imported": True}
    except Exception as exc:
        return {"module": module_name, "imported": False, "error": str(exc)}


def _flow_check() -> Dict[str, Any]:
    hello_intent = classify_intent("hello")
    auto_intent = classify_intent("/auto build a demo")
    return {
        "hello_intent": hello_intent.name,
        "hello_is_conversational": hello_intent == Intent.CONVERSATION,
        "autonomy_intent": auto_intent.name,
        "auto_triggers_autonomy": auto_intent == Intent.AUTONOMY_TRIGGER,
    }


def generate_report() -> Dict[str, Any]:
    repo_root = _find_repo_root()
    memory_dir = _resolve_storage_path("SENTINEL_STORAGE_DIR", _memory_default_dir())
    project_dir = _resolve_storage_path("SENTINEL_PROJECT_STORAGE", _project_default_dir())

    return {
        "repo_root": str(repo_root),
        "python": {
            "executable": sys.executable,
            "version": sys.version,
            "venv_active": _venv_active(),
        },
        "storage": {
            "SENTINEL_STORAGE_DIR": _probe_directory(memory_dir),
            "SENTINEL_PROJECT_STORAGE": _probe_directory(project_dir),
        },
        "imports": [
            _import_check("sentinel.controller"),
            _import_check("sentinel.conversation.conversation_controller"),
            _import_check("sentinel.gui.app"),
        ],
        "flow_checks": _flow_check(),
    }


def main() -> None:
    report = generate_report()
    print("=== Sentinel Doctor ===")
    print(f"Repository root: {report['repo_root']}")
    print("--- Python ---")
    print(f"Executable: {report['python']['executable']}")
    print(f"Version: {report['python']['version']}")
    print(f"Virtualenv active: {report['python']['venv_active']}")
    print("--- Storage ---")
    for name, details in report["storage"].items():
        print(f"{name}: {details['path']}")
        print(f"  Writable: {details.get('write')}")
        print(f"  Readback OK: {details.get('read')}")
        print(f"  Cleanup: {details.get('cleanup')}")
        if details.get("error"):
            print(f"  Error: {details['error']}")
        if details.get("cleanup_error"):
            print(f"  Cleanup error: {details['cleanup_error']}")
    print("--- Imports ---")
    for item in report["imports"]:
        status = "OK" if item.get("imported") else "FAILED"
        print(f"{item['module']}: {status}")
        if item.get("error"):
            print(f"  Error: {item['error']}")
    print("--- Flow checks ---")
    flow = report["flow_checks"]
    print(
        f"hello intent: {flow['hello_intent']} (conversational={flow['hello_is_conversational']})"
    )
    print(
        f"/auto intent: {flow['autonomy_intent']} (autonomy={flow['auto_triggers_autonomy']})"
    )


if __name__ == "__main__":
    main()
