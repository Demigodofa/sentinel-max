"""Sandbox for executing tool calls with restricted globals."""
from __future__ import annotations

from types import MappingProxyType
from typing import Any, Callable, Dict


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
    }
)


class SandboxError(Exception):
    pass


class Sandbox:
    """Execute callables in a constrained environment."""

    def __init__(self) -> None:
        self._globals: Dict[str, Any] = {"__builtins__": SAFE_BUILTINS}

    def execute(self, func: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
        try:
            # Avoid exposing caller globals by rebinding __globals__ when possible
            if hasattr(func, "__globals__"):
                func.__globals__.update({"__builtins__": SAFE_BUILTINS})
            return func(*args, **kwargs)
        except Exception as exc:  # pragma: no cover - defensive
            raise SandboxError(str(exc)) from exc
