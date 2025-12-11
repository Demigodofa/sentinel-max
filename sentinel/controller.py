"""Sentinel MAX controller orchestrating Agent Core components."""
from __future__ import annotations

from sentinel.agent_core.autonomy import AutonomyLoop
from sentinel.agent_core.planner import Planner
from sentinel.agent_core.worker import Worker
from sentinel.agent_core.sandbox import Sandbox
from sentinel.agent_core.reflection import Reflector
from sentinel.agent_core.self_mod import SelfModificationEngine
from sentinel.agent_core.patch_auditor import PatchAuditor
from sentinel.agent_core.hot_reloader import HotReloader
from sentinel.memory.memory_manager import MemoryManager
from sentinel.tools.registry import DEFAULT_TOOL_REGISTRY
from sentinel.tools import web_search, internet_extractor
from sentinel.tools.tool_generator import generate_echo_tool
from sentinel.logging.logger import get_logger

logger = get_logger(__name__)


class SentinelController:
    def __init__(self) -> None:
        self.memory = MemoryManager()
        self.tool_registry = DEFAULT_TOOL_REGISTRY
        self.sandbox = Sandbox()
        self._register_default_tools()

        self.planner = Planner(self.tool_registry, memory=self.memory)
        self.worker = Worker(self.tool_registry, self.sandbox, memory=self.memory)
        self.reflector = Reflector(self.memory)
        self.autonomy = AutonomyLoop(self.planner, self.worker, self.reflector, self.memory)

        self.patch_auditor = PatchAuditor()
        self.self_mod = SelfModificationEngine(self.patch_auditor)
        self.hot_reloader = HotReloader()

    def _register_default_tools(self) -> None:
        self.tool_registry.register("web_search", web_search.search)
        self.tool_registry.register("internet_extract", internet_extractor.extract)
        self.tool_registry.register("echo", generate_echo_tool(prefix="Echo: "))

    def process_input(self, message: str) -> str:
        logger.info("Processing user input: %s", message)
        trace = self.autonomy.run(message, max_time=2.0)
        latest_reflection = self.memory.latest("reflection")
        if latest_reflection:
            return latest_reflection.content
        return trace.summary()

    def export_state(self):
        return {
            "memory": self.memory.export_state(),
            "tools": list(self.tool_registry.list_tools().keys()),
        }
