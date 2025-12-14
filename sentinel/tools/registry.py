"""Tool registry and dispatch for Sentinel MAX."""
from __future__ import annotations

import importlib
import re
import shlex
import threading
from copy import deepcopy
from typing import Any, Callable, Dict, Optional

from sentinel.agent_core.base import Tool
from sentinel.logging.logger import get_logger
from sentinel.tools.tool_schema import ToolSchema, ToolValidator

logger = get_logger(__name__)


class ToolRegistry:
    """Registry for deterministic :class:`Tool` instances.

    The registry enforces name uniqueness, type-safety, and supports dynamic
    loading of tools by module path. All tools are expected to be safe and
    sandbox-friendly, with execution delegated to the global :class:`Sandbox`
    managed by the worker.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}
        self._schemas: Dict[str, ToolSchema] = {}
        self._lock = threading.RLock()
        self._event_sink: Callable[[Dict[str, Any]], None] | None = None

    # ------------------------------------------------------------------
    # Registration utilities
    # ------------------------------------------------------------------
    def register(self, tool: Tool) -> None:
        """Register a :class:`Tool` instance by its unique name."""

        schema = getattr(tool, "schema", None)
        if not isinstance(schema, ToolSchema):
            raise TypeError(f"Tool '{getattr(tool, 'name', '<unknown>')}' missing ToolSchema metadata")
        ToolValidator.validate(tool, schema)

        with self._lock:
            if tool.name in self._tools:
                raise ValueError(f"Tool '{tool.name}' is already registered")
            self._tools[tool.name] = tool
            self._schemas[tool.name] = schema
            logger.info("Registered tool: %s", tool.name)

    def set_event_sink(self, sink: Callable[[Dict[str, Any]], None] | None) -> None:
        """Set an optional sink for emitting telemetry events."""

        with self._lock:
            self._event_sink = sink
            logger.info("Tool registry event sink configured: %s", bool(sink))

    def _emit(self, event: Dict[str, Any]) -> None:
        sink = self._event_sink
        if not sink:
            return
        try:
            sink(event)
        except Exception:  # pragma: no cover - defensive logging
            logger.exception("Failed to emit tool registry event: %s", event)

    def load_dynamic(self, module_path: str, attribute: str | None = None) -> Tool:
        """Dynamically load and register a tool from a module path.

        Parameters
        ----------
        module_path: str
            Dotted module path (``package.module``) to import.
        attribute: str | None
            Optional attribute name to fetch from the imported module. When
            omitted, the loader will look for a ``tool`` or ``Tool`` symbol.
        """

        module = importlib.import_module(module_path)
        candidate_name = attribute or "tool"
        tool_obj = getattr(module, candidate_name, None) or getattr(
            module, candidate_name.capitalize(), None
        )
        if tool_obj is None:
            raise AttributeError(f"Module {module_path} does not expose a tool")
        if isinstance(tool_obj, type) and issubclass(tool_obj, Tool):
            tool_instance = tool_obj()  # type: ignore[call-arg]
        elif isinstance(tool_obj, Tool):
            tool_instance = tool_obj
        else:
            raise TypeError("Loaded object is not a Tool subclass or instance")
        self.register(tool_instance)
        return tool_instance

    # ------------------------------------------------------------------
    # Lookup utilities
    # ------------------------------------------------------------------
    def get(self, name: str) -> Tool:
        with self._lock:
            if name not in self._tools:
                raise KeyError(f"Tool '{name}' not registered")
            return self._tools[name]

    def get_schema(self, name: str) -> Optional[ToolSchema]:
        with self._lock:
            return self._schemas.get(name)

    def call(self, name: str, **kwargs):
        tool = self.get(name)
        schema = self.get_schema(name)
        normalized_kwargs = self._normalize_args(name, kwargs, schema)
        logger.info("Executing tool %s with %s", name, normalized_kwargs)

        try:
            return tool.execute(**normalized_kwargs)
        except TypeError as exc:
            arg = self._parse_unexpected_kwarg(exc)
            if arg is None or arg not in normalized_kwargs:
                raise
            repaired_kwargs = {k: v for k, v in normalized_kwargs.items() if k != arg}
            self._emit({"event": "tool_repair", "tool": name, "dropped_arg": arg})
            logger.warning("Retrying tool %s without arg '%s' after unexpected keyword error", name, arg)
            return tool.execute(**repaired_kwargs)

    def list_tools(self) -> Dict[str, Tool]:
        with self._lock:
            return dict(self._tools)

    def describe_tools(self) -> Dict[str, Dict]:
        with self._lock:
            return {name: schema.to_dict() for name, schema in self._schemas.items()}

    def has_tool(self, name: str) -> bool:
        with self._lock:
            return name in self._tools

    def prompt_safe_summary(self) -> Dict[str, Dict[str, Any]]:
        """Return a read-only view of tool metadata suitable for prompts."""

        with self._lock:
            summary: Dict[str, Dict[str, Any]] = {}
            for name, schema in self._schemas.items():
                inputs = {
                    field: {
                        "type": details.get("type", "any"),
                        "description": details.get("description", ""),
                        "required": bool(details.get("required", False)),
                    }
                    for field, details in schema.input_schema.items()
                }
                summary[name] = {
                    "description": schema.description,
                    "deterministic": schema.deterministic,
                    "permissions": list(schema.permissions),
                    "inputs": inputs,
                    "outputs": deepcopy(schema.output_schema),
                }
            return summary

    def _normalize_args(
        self, name: str, kwargs: Dict[str, Any], schema: Optional[ToolSchema]
    ) -> Dict[str, Any]:
        if schema is None:
            return kwargs

        input_schema = schema.input_schema or {}
        alias_map: Dict[str, Dict[str, str]] = {
            "web_search": {
                "num_results": "max_results",
                "k": "max_results",
                "limit": "max_results",
                "top_k": "max_results",
            },
            "microservice_builder": {"endpoints": "description"},
            "sandbox_exec": {"command": "argv"},
        }
        normalized: Dict[str, Any] = dict(kwargs)

        for alias, target in alias_map.get(name, {}).items():
            if alias in normalized and target not in normalized:
                normalized[target] = normalized.pop(alias)
            else:
                normalized.pop(alias, None)

        if name == "sandbox_exec" and isinstance(normalized.get("argv"), str):
            normalized["argv"] = shlex.split(normalized["argv"])

        if name == "web_search" and "max_results" in normalized:
            try:
                normalized["max_results"] = int(normalized["max_results"])
            except (TypeError, ValueError):
                pass

        if name == "microservice_builder" and "description" not in normalized:
            if "endpoints" in kwargs:
                normalized["description"] = kwargs["endpoints"]

        if input_schema == {}:
            return normalized

        allowed_keys = set(input_schema.keys())
        if "*" in allowed_keys:
            return normalized

        filtered = {k: v for k, v in normalized.items() if k in allowed_keys}
        missing_required = {
            key
            for key, details in input_schema.items()
            if details.get("required") and key not in filtered
        }
        if missing_required:
            self._emit(
                {
                    "event": "tool_args_missing",
                    "tool": name,
                    "missing": sorted(missing_required),
                }
            )
        dropped_keys = set(normalized).difference(filtered)
        if dropped_keys:
            self._emit(
                {
                    "event": "tool_args_normalized",
                    "tool": name,
                    "dropped": sorted(dropped_keys),
                }
            )
        return filtered

    @staticmethod
    def _parse_unexpected_kwarg(exc: TypeError) -> str | None:
        match = re.search(r"unexpected keyword argument '([^']+)'", str(exc))
        if match:
            return match.group(1)
        return None


# Singleton registry for convenience
DEFAULT_TOOL_REGISTRY = ToolRegistry()
