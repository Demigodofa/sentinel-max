"""Sentinel MAX controller orchestrating Agent Core components."""
from __future__ import annotations

from sentinel.agent_core.autonomy import AutonomyLoop
from sentinel.agent_core.worker import Worker
from sentinel.agent_core.sandbox import Sandbox
from sentinel.agent_core.reflection import Reflector
from sentinel.agent_core.self_mod import SelfModificationEngine
from sentinel.agent_core.patch_auditor import PatchAuditor
from sentinel.agent_core.hot_reloader import HotReloader
from sentinel.memory.memory_manager import MemoryManager
from sentinel.memory.intelligence import MemoryContextBuilder
from sentinel.planning.adaptive_planner import AdaptivePlanner
from sentinel.policy.policy_engine import PolicyEngine
from sentinel.reflection.reflection_engine import ReflectionEngine
from sentinel.tools.registry import DEFAULT_TOOL_REGISTRY
from sentinel.tools.web_search import WEB_SEARCH_TOOL
from sentinel.tools.internet_extractor import INTERNET_EXTRACTOR_TOOL
from sentinel.tools.code_analyzer import CODE_ANALYZER_TOOL
from sentinel.tools.microservice_builder import MICROSERVICE_BUILDER_TOOL
from sentinel.tools.tool_generator import generate_echo_tool
from sentinel.logging.logger import get_logger

logger = get_logger(__name__)


class SentinelController:
    def __init__(self) -> None:
        self.memory = MemoryManager()
        self.tool_registry = DEFAULT_TOOL_REGISTRY
        self.sandbox = Sandbox()
        self.memory_context_builder = MemoryContextBuilder(self.memory)
        self.policy_engine = PolicyEngine(self.memory)
        self._register_default_tools()

        self.planner = AdaptivePlanner(
            self.tool_registry, memory=self.memory, policy_engine=self.policy_engine, memory_context_builder=self.memory_context_builder
        )
        self.worker = Worker(
            self.tool_registry, self.sandbox, memory=self.memory, policy_engine=self.policy_engine
        )
        self.reflection_engine = ReflectionEngine(self.memory, policy_engine=self.policy_engine, memory_context_builder=self.memory_context_builder)
        self.reflector = Reflector(self.memory, self.reflection_engine)
        self.autonomy = AutonomyLoop(
            self.planner,
            self.worker,
            self.reflector,
            self.memory,
            cycle_limit=3,
            timeout=5.0,
        )

        self.patch_auditor = PatchAuditor()
        self.self_mod = SelfModificationEngine(self.patch_auditor)
        self.hot_reloader = HotReloader()

    def _register_default_tools(self) -> None:
        self.tool_registry.register(WEB_SEARCH_TOOL)
        self.tool_registry.register(INTERNET_EXTRACTOR_TOOL)
        self.tool_registry.register(CODE_ANALYZER_TOOL)
        self.tool_registry.register(MICROSERVICE_BUILDER_TOOL)
        generate_echo_tool(prefix="Echo: ", registry=self.tool_registry)

    def process_input(self, message: str) -> str:
        logger.info("Processing user input: %s", message)
        trace = self.autonomy.run(message, timeout=2.0)
        latest_reflection = self.memory.latest("reflection.operational") or self.memory.latest(
            "reflection"
        )
        if latest_reflection:
            return latest_reflection.content
        return trace.summary()

    def export_state(self):
        tools = {
            name: getattr(tool, "description", "") for name, tool in self.tool_registry.list_tools().items()
        }
        return {"memory": self.memory.export_state(), "tools": tools}
