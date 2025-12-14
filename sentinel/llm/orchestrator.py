"""OpenAI tool-calling orchestrator for Sentinel tools."""
from __future__ import annotations

import json
import time
from typing import Any, Dict, Iterable, Optional

from sentinel.agent_core.sandbox import Sandbox, SandboxError
from sentinel.config.sandbox_config import ensure_sandbox_root_exists
from sentinel.logging.logger import get_logger
from sentinel.memory.memory_manager import MemoryManager
from sentinel.tools.registry import ToolRegistry


logger = get_logger(__name__)


class ToolCallingOrchestrator:
    """Drive real tool execution via OpenAI tool/function calling."""

    def __init__(
        self,
        llm_client,
        tool_registry: ToolRegistry,
        sandbox: Sandbox,
        *,
        memory: MemoryManager | None = None,
        max_rounds: int = 4,
    ) -> None:
        self.llm_client = llm_client
        self.tool_registry = tool_registry
        self.sandbox = sandbox
        self.memory = memory
        self.max_rounds = max_rounds
        self._tool_definitions = self._build_tool_definitions()

    def should_route(self, text: str) -> bool:
        normalized = text.strip().lower()
        if not normalized:
            return False
        if normalized.startswith("action:") or normalized.startswith("tool:"):
            return True
        if normalized.startswith("/"):
            name = normalized.split()[0].lstrip("/")
            return self.tool_registry.has_tool(name)
        keywords = ("fs_", "list files", "search web", "web search", "summarize sources", "list tools")
        return any(key in normalized for key in keywords)

    def handle(
        self,
        text: str,
        *,
        stage_logger=None,
        session_context: Optional[Dict[str, object]] = None,
    ) -> Dict[str, object]:
        """Run the tool-calling orchestration loop and return a response payload."""

        if not getattr(self.llm_client, "supports_tool_calls", lambda: False)():
            message = "Tool calling is unavailable for this LLM backend."
            return self._payload(message, session_context=session_context)

        seeded_call = self._extract_direct_call(text)
        messages: list[dict[str, object]] = [
            {
                "role": "system",
                "content": (
                    "You are Sentinel's orchestrator. Use the provided tools to satisfy the request. "
                    "Do not claim you executed a tool unless you invoked it and received output. "
                    "Keep execution within the sandbox root and report when access is denied."
                ),
            }
        ]

        messages.append({"role": "user", "content": text})

        tool_trace: list[dict[str, Any]] = []
        rounds = 0
        pending_calls = [seeded_call] if seeded_call else []
        while rounds < self.max_rounds:
            rounds += 1
            if pending_calls:
                messages.append({"role": "assistant", "content": None, "tool_calls": pending_calls})
                tool_messages: list[dict[str, object]] = []
                for call in pending_calls:
                    tool_name, args = self._parse_tool_call(call)
                    result = self._execute_tool(tool_name, args, stage_logger)
                    tool_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.get("id"),
                            "name": tool_name,
                            "content": json.dumps(result, ensure_ascii=False),
                        }
                    )
                    tool_trace.append({"tool": tool_name, "args": args, "result": result})
                messages.extend(tool_messages)
                pending_calls = []

            response = self.llm_client.chat_with_tools(messages, self._tool_definitions)
            if response is None:
                return self._payload("LLM tool-call request failed; no actions were run.", tool_trace, session_context)

            tool_calls = response.get("tool_calls") or []
            assistant_content = response.get("content")
            messages.append({"role": "assistant", "content": assistant_content, "tool_calls": tool_calls})

            if not tool_calls:
                if assistant_content:
                    final = assistant_content
                elif tool_trace:
                    executed = ", ".join({trace.get("tool", "unknown") for trace in tool_trace})
                    final = f"Executed tools: {executed}. No model summary returned."
                else:
                    final = "No actions executed."
                return self._payload(final, tool_trace, session_context)

            pending_calls = tool_calls

        return self._payload(
            "Reached max orchestration turns without a final response.", tool_trace, session_context
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _build_tool_definitions(self) -> list[dict[str, object]]:
        definitions: list[dict[str, object]] = []
        for name, schema in self.tool_registry.describe_tools().items():
            properties, required = self._normalize_input_schema(schema.get("input_schema"))
            definitions.append(
                {
                    "type": "function",
                    "function": {
                        "name": schema.get("name") or name,
                        "description": schema.get("description", ""),
                        "parameters": {
                            "type": "object",
                            "properties": properties,
                            "required": required,
                        },
                    },
                }
            )
        return definitions

    def _normalize_input_schema(
        self, input_schema: object
    ) -> tuple[dict[str, dict[str, object]], list[str]]:
        properties: dict[str, dict[str, object]] = {}
        required: list[str] = []

        if not isinstance(input_schema, dict):
            return properties, required

        # Support JSON Schema-style definitions with nested properties and explicit required fields.
        if "properties" in input_schema:
            nested_properties = input_schema.get("properties") or {}
            if isinstance(nested_properties, dict):
                for field, details in nested_properties.items():
                    if not isinstance(details, dict):
                        continue
                    properties[field] = {
                        "type": self._map_type(details.get("type")),
                        "description": details.get("description", ""),
                    }
            nested_required = input_schema.get("required") or []
            if isinstance(nested_required, (list, tuple)):
                required = [str(field) for field in nested_required]
            return properties, required

        # Default to simple field metadata map.
        for field, details in input_schema.items():
            if not isinstance(details, dict):
                continue
            properties[field] = {
                "type": self._map_type(details.get("type")),
                "description": details.get("description", ""),
            }
            if details.get("required"):
                required.append(field)

        return properties, required

    def _extract_direct_call(self, text: str) -> dict[str, object] | None:
        normalized = text.strip()
        if normalized.lower().startswith("action:"):
            return self._seed_call_from_tokens(normalized[7:].strip())
        if normalized.lower().startswith("tool:"):
            return self._seed_call_from_tokens(normalized[5:].strip())
        if normalized.startswith("/"):
            candidate = normalized.lstrip("/")
            return self._seed_call_from_tokens(candidate)
        return None

    def _seed_call_from_tokens(self, token_blob: str) -> dict[str, object] | None:
        if not token_blob:
            return None
        parts = token_blob.split(" ", 1)
        tool_name = parts[0].strip()
        if not self.tool_registry.has_tool(tool_name):
            return None
        raw_args = (parts[1] if len(parts) > 1 else "{}").strip()
        try:
            parsed_args = json.loads(raw_args) if raw_args else {}
        except Exception:
            parsed_args = {}
        if not isinstance(parsed_args, dict):
            parsed_args = {}
        return {
            "id": f"seeded-{int(time.time()*1000)}",
            "type": "function",
            "function": {"name": tool_name, "arguments": json.dumps(parsed_args)},
        }

    def _parse_tool_call(self, call: dict[str, object]) -> tuple[str, dict[str, Any]]:
        fn = call.get("function") if isinstance(call, dict) else {}
        tool_name = ""
        args: dict[str, Any] = {}
        if isinstance(fn, dict):
            tool_name = str(fn.get("name") or "")
            raw_args = fn.get("arguments") or "{}"
            if isinstance(raw_args, str):
                try:
                    args = json.loads(raw_args) if raw_args.strip() else {}
                except Exception:
                    args = {}
            elif isinstance(raw_args, dict):
                args = raw_args
        return tool_name, args

    def _execute_tool(self, tool_name: str, args: dict[str, Any], stage_logger=None) -> dict[str, Any]:
        if not self.tool_registry.has_tool(tool_name):
            return {"ok": False, "error": "unknown_tool", "tool": tool_name}

        sandbox_root = ensure_sandbox_root_exists()
        try:
            output = self.sandbox.execute(self.tool_registry.call, tool_name, **args)
            success = True
        except PermissionError as exc:
            output = {
                "ok": False,
                "error": "sandbox_violation",
                "message": str(exc),
                "sandbox_root": str(sandbox_root),
            }
            success = False
        except SandboxError as exc:
            output = {"ok": False, "error": "sandbox_error", "message": str(exc)}
            success = False
        except Exception as exc:  # pragma: no cover - defensive
            output = {"ok": False, "error": "execution_failed", "message": str(exc)}
            success = False

        if stage_logger:
            stage_logger.log_execute(
                "tool_call",
                tool=tool_name,
                success=success,
                correlation_id=getattr(stage_logger, "correlation_id", None),
            )

        if self.memory:
            metadata = {
                "tool": tool_name,
                "args": args,
                "success": success,
                "output": output,
                "timestamp": time.time(),
                "type": "orchestrator_execution",
            }
            try:
                self.memory.store_fact("execution_real", key=None, value=metadata)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.warning("Failed to persist orchestrator execution: %s", exc)

        return output if isinstance(output, dict) else {"ok": success, "output": output}

    def _map_type(self, input_type: Optional[str]) -> str:
        normalized = (input_type or "string").lower()
        if normalized in {"int", "integer"}:
            return "integer"
        if normalized in {"bool", "boolean"}:
            return "boolean"
        if normalized in {"number", "float"}:
            return "number"
        return "string"

    def _payload(
        self,
        response: str,
        tool_trace: Optional[Iterable[dict[str, Any]]] = None,
        session_context: Optional[Dict[str, object]] = None,
    ) -> Dict[str, object]:
        return {
            "response": response,
            "normalized_goal": None,
            "task_graph": None,
            "trace": list(tool_trace or []),
            "dialog_context": session_context or {},
        }

