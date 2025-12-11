"""Tool registry and dispatch for Sentinel MAX."""
from __future__ import annotations

from typing import Callable, Dict, Any

from sentinel.logging.logger import get_logger

logger = get_logger(__name__)


class ToolRegistry:
    """Registry for callable tools.

    Tools are registered under a string name. Each tool is a callable that
    accepts keyword arguments. All tool executions are expected to be safe and
    deterministic to keep planning reproducible.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, Callable[..., Any]] = {}

    def register(self, name: str, func: Callable[..., Any]) -> None:
        if name in self._tools:
            logger.warning("Tool %s already registered; overriding", name)
        self._tools[name] = func

    def call(self, name: str, **kwargs: Any) -> Any:
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not registered")
        logger.info("Executing tool %s with %s", name, kwargs)
        return self._tools[name](**kwargs)

    def list_tools(self) -> Dict[str, Callable[..., Any]]:
        return dict(self._tools)

    def has_tool(self, name: str) -> bool:
        return name in self._tools


# Singleton registry for convenience
DEFAULT_TOOL_REGISTRY = ToolRegistry()
