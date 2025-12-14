"""Conversational orchestrator that drives tools automatically."""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sentinel.logging.logger import get_logger
from sentinel.memory.memory_manager import MemoryManager
from sentinel.orchestration.optimizer import Optimizer
from sentinel.orchestration.plan_publisher import PlanPublisher
from sentinel.orchestration.tool_builder import ToolBuilder
from sentinel.reflection.reflection_engine import ReflectionEngine
from sentinel.tools.registry import ToolRegistry

logger = get_logger(__name__)

RISKY_TOOLS = {"fs_delete", "fs_write", "pip_install", "kill_process"}


def tool_schema_to_openai(tool_name: str, schema_dict: dict) -> dict:
    inputs = schema_dict.get("inputs", {}) or schema_dict.get("input_schema", {}) or {}
    props: dict[str, dict[str, str]] = {}
    required: list[str] = []

    if isinstance(inputs, dict) and "properties" in inputs:
        nested_props = inputs.get("properties") or {}
        if isinstance(nested_props, dict):
            for field, meta in nested_props.items():
                if not isinstance(meta, dict):
                    continue
                props[field] = {
                    "type": meta.get("type", "string"),
                    "description": meta.get("description", ""),
                }
        if isinstance(inputs.get("required"), (list, tuple)):
            required.extend(str(item) for item in inputs.get("required", []))
    elif isinstance(inputs, dict):
        for k, meta in inputs.items():
            if not isinstance(meta, dict):
                continue
            props[k] = {
                "type": meta.get("type", "string"),
                "description": meta.get("description", ""),
            }
            if meta.get("required"):
                required.append(k)

    return {
        "type": "function",
        "function": {
            "name": tool_name,
            "description": schema_dict.get("description", ""),
            "parameters": {
                "type": "object",
                "properties": props,
                "required": required,
                "additionalProperties": True,
            },
        },
    }


class Orchestrator:
    """Run LLM-guided tool calls with plan publishing and safety gates."""

    def __init__(
        self,
        llm_client,
        tool_registry: ToolRegistry,
        memory: MemoryManager,
        *,
        reflection_engine: Optional[ReflectionEngine] = None,
        optimizer: Optional[Optimizer] = None,
        max_steps: Optional[int] = None,
    ) -> None:
        self.llm_client = llm_client
        self.tool_registry = tool_registry
        self.memory = memory
        self.reflection_engine = reflection_engine
        self.optimizer = optimizer or Optimizer(tool_registry, memory)
        self.plan_publisher = PlanPublisher(memory)
        self.tool_builder = ToolBuilder(tool_registry, memory)
        self.max_steps = max_steps or int(os.environ.get("MAX_STEPS", 12))
        self._pending_confirmation: Optional[Dict[str, Any]] = None
        self._current_plan_id: Optional[str] = None

    @property
    def awaiting_confirmation(self) -> bool:
        return self._pending_confirmation is not None

    def should_route(self, text: str) -> bool:
        return False

    def handle(
        self,
        text: str,
        *,
        stage_logger=None,
        session_context: Optional[Dict[str, object]] = None,
    ) -> Dict[str, object]:
        response = self.run(text, auto=True)
        return {
            "response": response,
            "normalized_goal": None,
            "task_graph": None,
            "trace": None,
            "dialog_context": session_context,
        }

    def run(self, user_text: str, *, auto: bool = True) -> str:
        goal = user_text.strip()
        self._current_plan_id = self.plan_publisher.publish_plan(goal, steps=[])
        messages: List[Dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are Sentinel's autonomous orchestrator. Build a short plan, call tools to execute it, "
                    "and return a concise summary. Do not expose chain-of-thought."
                ),
            },
            {"role": "user", "content": goal},
        ]
        tool_schemas = []
        for name, schema in self.tool_registry.describe_tools().items():
            schema_dict = schema.to_dict() if hasattr(schema, "to_dict") else schema
            tool_schemas.append(tool_schema_to_openai(name, schema_dict))
        step_counter = 0
        tool_events: List[Dict[str, Any]] = []
        tool_calls_trace: List[Dict[str, Any]] = []

        while step_counter < self.max_steps:
            step_counter += 1
            response = self.llm_client.chat_with_tools(messages, tool_schemas)
            if response is None:
                return "LLM tool-call request failed; no actions were run."

            tool_calls = response.get("tool_calls") or []
            assistant_content = response.get("content")
            if tool_calls:
                messages.append({"role": "assistant", "content": assistant_content, "tool_calls": tool_calls})
                for call in tool_calls:
                    tool_name, args = self._parse_tool_call(call)
                    plan_step_id = len(tool_calls_trace) + 1
                    self.plan_publisher.update_step(
                        self._current_plan_id,
                        plan_step_id,
                        status="running",
                        description=f"Execute {tool_name}",
                        tool_name=tool_name,
                        params=args,
                    )
                    if tool_name in RISKY_TOOLS:
                        self._pending_confirmation = {
                            "tool": tool_name,
                            "args": args,
                            "call": call,
                            "plan_step_id": plan_step_id,
                            "goal": goal,
                        }
                        self.memory.store_fact("pending_actions", key=None, value=self._pending_confirmation)
                        self.plan_publisher.update_step(
                            self._current_plan_id,
                            plan_step_id,
                            status="awaiting_confirmation",
                            note="Awaiting user confirmation",
                        )
                        return (
                            f"About to run {tool_name} with args {args}. This may be destructive. "
                            "Proceed? (yes/no)"
                        )

                    if not self.tool_registry.has_tool(tool_name):
                        gap_note = args.get("reason") if isinstance(args, dict) else ""
                        self.plan_publisher.update_step(
                            self._current_plan_id,
                            plan_step_id,
                            status="running",
                            note=f"Tool gap detected: {tool_name} {gap_note}",
                        )
                        built = self.tool_builder.build_tool(
                            tool_name,
                            purpose=gap_note or f"Auto-generated tool for {goal}",
                            inputs={},
                            outputs={},
                        )
                        tool_events.append({"event": "tool_built", "tool": tool_name, "metadata": built})

                    result = self._execute_tool(tool_name, args)
                    tool_calls_trace.append({"tool": tool_name, "args": args, "result": result})
                    status = "done" if result.get("ok", True) else "failed"
                    self.plan_publisher.update_step(
                        self._current_plan_id,
                        plan_step_id,
                        status=status,
                        note=result.get("message") or result.get("error"),
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.get("id", str(uuid4())),
                            "name": tool_name,
                            "content": json.dumps(result, ensure_ascii=False),
                        }
                    )
                    tool_events.append({"tool": tool_name, "args": args, "result": result})
                continue

            messages.append({"role": "assistant", "content": assistant_content, "tool_calls": []})
            final_message = assistant_content or "No actions executed."
            reflection = None
            if self.reflection_engine:
                try:
                    reflection = self.reflection_engine.reflect(tool_calls_trace, goal=goal)
                except Exception:  # pragma: no cover - defensive
                    logger.warning("Reflection failed", exc_info=True)
            optimizer_result = self.optimizer.optimize(tool_events=tool_events, reflections=reflection)
            self.plan_publisher.update_step(
                self._current_plan_id,
                step_counter + 1,
                status="done",
                description="Optimizer applied",
                note=optimizer_result.get("message"),
            )
            return final_message

        return "Reached max orchestration turns without a final response."

    def handle_confirmation(self, answer: str) -> str:
        if not self._pending_confirmation:
            return "No pending actions to confirm."
        normalized = answer.strip().lower()
        plan_step_id = self._pending_confirmation.get("plan_step_id", 0)
        if normalized in {"yes", "y", "ok", "go", "proceed"}:
            tool_name = self._pending_confirmation.get("tool")
            args = self._pending_confirmation.get("args", {})
            result = self._execute_tool(tool_name, args)
            status = "done" if result.get("ok", True) else "failed"
            self.plan_publisher.update_step(
                self._current_plan_id,
                plan_step_id,
                status=status,
                note=result.get("message") or result.get("error"),
            )
            self._pending_confirmation = None
            return json.dumps(result)

        interpretations = [
            "You might have wanted a dry-run instead of deletion.",
            "You may prefer archiving files over removing them.",
            "The requested cleanup might be too broad.",
        ]
        correction = {
            "assumption": self._pending_confirmation.get("goal", ""),
            "action": self._pending_confirmation.get("tool"),
            "args": self._pending_confirmation.get("args", {}),
            "feedback": answer,
        }
        self.memory.store_fact("intent_rules", key=None, value=correction)
        self.plan_publisher.update_step(
            self._current_plan_id,
            plan_step_id,
            status="failed",
            note="User declined the action",
        )
        self._pending_confirmation = None
        return (
            "Why did you assume I wanted that? Here are 2–3 interpretations: "
            + " | ".join(interpretations)
        )

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

    def _execute_tool(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        if not self.tool_registry.has_tool(tool_name):
            return {"ok": False, "error": "unknown_tool", "tool": tool_name}
        try:
            output = self.tool_registry.call(tool_name, **args)
            success = True
        except Exception as exc:  # pragma: no cover - defensive
            output = {"ok": False, "error": "execution_failed", "message": str(exc)}
            success = False
        result = output if isinstance(output, dict) else {"ok": success, "output": output}
        self.memory.store_fact(
            "execution_real",
            key=None,
            value={"tool": tool_name, "args": args, "success": success, "output": result, "timestamp": time.time()},
        )
        return result
