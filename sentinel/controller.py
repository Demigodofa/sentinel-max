"""Sentinel MAX controller orchestrating Agent Core components."""
from __future__ import annotations

import json
from typing import Any

from sentinel.agent_core.autonomy import AutonomyLoop
from sentinel.agent_core.hot_reload import HotReloader
from sentinel.agent_core.patch_auditor import PatchAuditor
from sentinel.agent_core.reflection import Reflector
from sentinel.agent_core.sandbox import Sandbox
from sentinel.agent_core.self_mod import SelfModificationEngine
from sentinel.agent_core.worker import Worker
from sentinel.conversation import (
    ConversationController,
    DialogManager,
    IntentEngine,
    MessageDTO,
    NLToTaskGraph,
)
from sentinel.config.sandbox_config import ensure_sandbox_root_exists
from sentinel.execution.approval_gate import ApprovalGate
from sentinel.execution.execution_controller import ExecutionController
from sentinel.logging.logger import get_logger
from sentinel.llm.client import LLMClient
from sentinel.memory.intelligence import MemoryContextBuilder
from sentinel.memory.memory_manager import MemoryManager
from sentinel.planning.adaptive_planner import AdaptivePlanner
from sentinel.policy.policy_engine import PolicyEngine
from sentinel.reflection.reflection_engine import ReflectionEngine
from sentinel.research.research_engine import AutonomousResearchEngine
from sentinel.simulation.sandbox import SimulationSandbox
from sentinel.tools import (
    FSDeleteTool,
    FSListTool,
    FSReadTool,
    FSWriteTool,
    SandboxExecTool,
    WebSearchTool,
)
from sentinel.tools.browser_agent import BrowserAgent
from sentinel.tools.code_analyzer import CODE_ANALYZER_TOOL
from sentinel.tools.internet_extractor import InternetExtractorTool
from sentinel.tools.microservice_builder import MICROSERVICE_BUILDER_TOOL
from sentinel.tools.registry import DEFAULT_TOOL_REGISTRY
from sentinel.tools.tool_generator import generate_echo_tool
from sentinel.world.model import WorldModel

logger = get_logger(__name__)


class SentinelController:
    def __init__(self) -> None:
        self.memory = MemoryManager()
        self.llm_client = LLMClient()
        self.world_model = WorldModel(self.memory)

        # NOTE: DEFAULT_TOOL_REGISTRY may be a singleton; duplicate registration can happen on reload.
        self.tool_registry = DEFAULT_TOOL_REGISTRY

        ensure_sandbox_root_exists()
        self.sandbox = Sandbox()

        self.simulation_sandbox = SimulationSandbox(self.tool_registry)
        self.memory_context_builder = MemoryContextBuilder(
            self.memory, tool_registry=self.tool_registry
        )
        self.policy_engine = PolicyEngine(self.memory)

        self._register_default_tools()

        self.research_engine = AutonomousResearchEngine(
            self.tool_registry,
            self.memory,
            self.policy_engine,
            simulation_sandbox=self.simulation_sandbox,
        )

        self.dialog_manager = DialogManager(self.memory, self.world_model, llm_client=self.llm_client)
        self.approval_gate = ApprovalGate(self.dialog_manager)

        self.intent_engine = IntentEngine(self.memory, self.world_model, self.tool_registry)
        self.nl_to_taskgraph = NLToTaskGraph(self.tool_registry, self.policy_engine, self.world_model)

        self.planner = AdaptivePlanner(
            self.tool_registry,
            memory=self.memory,
            policy_engine=self.policy_engine,
            memory_context_builder=self.memory_context_builder,
            world_model=self.world_model,
            simulation_sandbox=self.simulation_sandbox,
        )

        self.worker = Worker(
            self.tool_registry,
            self.sandbox,
            memory=self.memory,
            policy_engine=self.policy_engine,
            simulation_sandbox=self.simulation_sandbox,
            world_model=self.world_model,
            approval_gate=self.approval_gate,
        )

        self.execution_controller = ExecutionController(
            self.worker,
            self.policy_engine,
            self.approval_gate,
            self.dialog_manager,
            self.memory,
        )

        self.reflection_engine = ReflectionEngine(
            self.memory,
            policy_engine=self.policy_engine,
            memory_context_builder=self.memory_context_builder,
        )
        self.reflector = Reflector(self.memory, self.reflection_engine)

        self.autonomy = AutonomyLoop(
            self.planner,
            self.worker,
            self.execution_controller,
            self.reflector,
            self.memory,
            cycle_limit=5,
            timeout=None,
        )

        self.conversation_controller = ConversationController(
            dialog_manager=self.dialog_manager,
            intent_engine=self.intent_engine,
            nl_to_taskgraph=self.nl_to_taskgraph,
            autonomy=self.autonomy,
            planner=self.planner,
            memory=self.memory,
            world_model=self.world_model,
            simulation_sandbox=self.simulation_sandbox,
            llm_client=self.llm_client,
        )

        self.patch_auditor = PatchAuditor()
        self.self_mod = SelfModificationEngine(self.patch_auditor)
        self.hot_reloader = HotReloader()

        self.health_status = self._run_llm_health_check()

    def _run_llm_health_check(self) -> dict[str, Any]:
        ok, message = self.llm_client.health_check()
        payload = {
            "component": "llm",
            "text": message,
            "status": "ok" if ok else "error",
            "backend": self.llm_client.backend,
            "model": self.llm_client.cfg.model,
            "base_url": self.llm_client.cfg.base_url,
        }
        try:
            self.memory.store_fact("pipeline_events", key="llm_health", value=payload)
        except Exception as exc:  # pragma: no cover - defensive store
            logger.warning("Failed to record LLM health status: %s", exc)

        log_fn = logger.info if ok else logger.error
        log_fn("LLM startup health check: %s", message)
        return {"ok": ok, "message": message}

    def _register_default_tools(self) -> None:
        """Register built-in tools once per controller instance."""

        def safe_register(tool: Any) -> None:
            # Prefer has_tool if available; otherwise tolerate duplicates.
            try:
                has_tool = getattr(self.tool_registry, "has_tool", None)
                if callable(has_tool) and has_tool(tool.name):
                    return
                self.tool_registry.register(tool)
            except ValueError:
                # Tool already registered (or duplicate name) â€” ignore.
                return

        # Hard-sandboxed filesystem + exec
        safe_register(FSListTool())
        safe_register(FSReadTool())
        safe_register(FSWriteTool())
        safe_register(FSDeleteTool())
        safe_register(SandboxExecTool())

        # Network / analysis / builder tools
        safe_register(WebSearchTool(memory_manager=self.memory))
        safe_register(
            InternetExtractorTool(
                vector_memory=self.memory.vector,
                memory_manager=self.memory,
            )
        )
        safe_register(CODE_ANALYZER_TOOL)
        safe_register(MICROSERVICE_BUILDER_TOOL)
        safe_register(BrowserAgent())

        # Optional echo tool (guard against duplicate registration)
        try:
            generate_echo_tool(prefix="Echo: ", registry=self.tool_registry)
        except ValueError:
            pass

    def process_input(self, message: MessageDTO | str) -> str:
        dto = MessageDTO.coerce(message)
        command_response = self._handle_cli_command(dto.text)
        if command_response is not None:
            return command_response

        result = self.process_conversation(dto)
        return str(result.get("response", ""))

    def process_conversation(self, message: MessageDTO | str) -> dict[str, Any]:
        dto = MessageDTO.coerce(message)
        logger.info("Processing user input: %s", dto.text)
        return self.conversation_controller.handle_input(dto.text)

    def export_state(self) -> dict[str, Any]:
        tools = {
            name: getattr(tool, "description", "")
            for name, tool in self.tool_registry.list_tools().items()
        }
        world_model_state = self.memory.query("world_model", key="state")
        return {
            "memory": self.memory.export_state(),
            "tools": tools,
            "world_model": world_model_state,
        }

    def pipeline_snapshot(self, limit: int = 5) -> dict[str, list[dict[str, Any]]]:
        """Collect recent plan, execution, reflection, and policy records."""

        namespaces = [
            "plans",
            "execution",
            "execution_real",
            "policy_events",
            "pipeline_events",
        ]
        reflections = [ns for ns in self.memory.symbolic.list_namespaces() if ns.startswith("reflection")]
        snapshot: dict[str, list[dict[str, Any]]] = {}
        for ns in namespaces + reflections:
            records = self.memory.recall_recent(limit=limit, namespace=ns)
            if records:
                snapshot[ns] = records
        return snapshot

    # ------------------------------------------------------------------
    # CLI-only helper commands
    # ------------------------------------------------------------------
    def _handle_cli_command(self, message: str) -> str | None:
        if not message.startswith("/"):
            return None

        if message.strip() == "/tools":
            tools = sorted(self.tool_registry.list_tools().keys())
            return "Available tools: " + (", ".join(tools) if tools else "No tools registered.")

        if message.startswith("/tool"):
            parts = message.split(maxsplit=2)
            if len(parts) < 3:
                return "Usage: /tool <name> <json_args>"

            tool_name = parts[1]
            raw_args = parts[2]

            try:
                args = json.loads(raw_args) if raw_args else {}
            except json.JSONDecodeError as exc:
                return f"Invalid JSON args: {exc}"

            if not isinstance(args, dict):
                return "Tool arguments must be a JSON object."

            has_tool = getattr(self.tool_registry, "has_tool", None)
            if callable(has_tool):
                if not has_tool(tool_name):
                    return f"Tool '{tool_name}' not registered."
            else:
                if tool_name not in self.tool_registry.list_tools():
                    return f"Tool '{tool_name}' not registered."

            try:
                output = self.sandbox.execute(self.tool_registry.call, tool_name, **args)
                return str(output)
            except Exception as exc:  # pragma: no cover
                return f"Tool '{tool_name}' execution failed: {exc}"

        if message.strip() == "/state":
            snapshot = self.pipeline_snapshot(limit=3)
            if not snapshot:
                return "No pipeline state available."
            lines = []
            for namespace, records in snapshot.items():
                lines.append(f"[{namespace}]")
                for record in records:
                    meta = record.get("metadata", {}) or {}
                    correlation_id = meta.get("correlation_id") or record.get("value", {}).get("correlation_id") if isinstance(record.get("value"), dict) else None
                    summary = record.get("value")
                    if isinstance(summary, dict):
                        summary = summary.get("message") or summary.get("summary") or str(summary)
                    lines.append(f"  - {correlation_id or 'n/a'} :: {summary}")
            return "\n".join(lines)

        return None
