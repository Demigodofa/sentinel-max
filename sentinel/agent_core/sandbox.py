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
        func_globals: Dict[str, Any] | None = None
        had_builtins = False
        previous_builtins: Any | None = None

        try:
            # Avoid exposing caller globals by rebinding __globals__ when possible
            if hasattr(func, "__globals__"):
                func_globals = func.__globals__
                had_builtins = "__builtins__" in func_globals
                previous_builtins = func_globals.get("__builtins__")
                func_globals["__builtins__"] = SAFE_BUILTINS
            return func(*args, **kwargs)
        except Exception as exc:  # pragma: no cover - defensive
            raise SandboxError(str(exc)) from exc
        finally:
            if func_globals is not None:
                if had_builtins:
                    func_globals["__builtins__"] = previous_builtins
                else:
                    func_globals.pop("__builtins__", None)
