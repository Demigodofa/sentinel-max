import unittest

from sentinel.conversation.intent_engine import IntentEngine
from sentinel.conversation.nl_to_taskgraph import NLToTaskGraph
from sentinel.memory.memory_manager import MemoryManager
from sentinel.policy.policy_engine import PolicyEngine
from sentinel.tools.code_analyzer import CODE_ANALYZER_TOOL
from sentinel.tools.microservice_builder import MICROSERVICE_BUILDER_TOOL
from sentinel.tools.registry import ToolRegistry
from sentinel.tools.web_search import WEB_SEARCH_TOOL
from sentinel.world.model import WorldModel


class ConversationPipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.memory = MemoryManager()
        self.world_model = WorldModel(self.memory)
        self.registry = ToolRegistry()
        self.registry.register(WEB_SEARCH_TOOL)
        self.registry.register(CODE_ANALYZER_TOOL)
        self.registry.register(MICROSERVICE_BUILDER_TOOL)
        permissions = set()
        for tool in self.registry.list_tools().values():
            permissions.update(tool.schema.permissions)
        self.policy_engine = PolicyEngine(self.memory, allowed_permissions=permissions)
        self.intent_engine = IntentEngine(self.memory, self.world_model, self.registry)
        self.translator = NLToTaskGraph(self.registry, self.policy_engine, self.world_model)

    def test_simple_scraper_transcript(self) -> None:
        goal = "Make a scraper for this URL http://example.com"
        normalized = self.intent_engine.run(goal)
        self.assertEqual(normalized.source_intent.intent, "web_scraping")
        graph = self.translator.translate(normalized)
        node_ids = [node.id for node in graph]
        self.assertIn("collect_content", node_ids)
        self.assertTrue(any("validation" in node.id for node in graph))

    def test_multi_service_transcript(self) -> None:
        goal = "Build two microservices and connect them with a queue"
        normalized = self.intent_engine.run(goal)
        self.assertEqual(normalized.source_intent.intent, "build_microservice")
        graph = self.translator.translate(normalized)
        node_ids = [node.id for node in graph]
        self.assertIn("generate_service", node_ids)
        self.assertIn("connect_services", node_ids)

    def test_real_world_planning_transcript(self) -> None:
        goal = "Draft a strategy for optimizing my weekly workflow"
        normalized = self.intent_engine.run(goal)
        self.assertEqual(normalized.source_intent.intent, "schedule_planning")
        graph = self.translator.translate(normalized)
        self.assertIn("compose_plan", [node.id for node in graph])

    def test_browser_interaction_transcript(self) -> None:
        goal = "Go to this portal, log in, and fill out the form at http://portal.local"
        normalized = self.intent_engine.run(goal)
        self.assertIn("authenticate", normalized.parameters.get("browser_actions", []))
        self.assertIn("fill_form", normalized.parameters.get("browser_actions", []))
        graph = self.translator.translate(normalized)
        self.assertGreaterEqual(len(graph.nodes), 3)

    def test_optimization_transcript(self) -> None:
        goal = "Rewrite the compression tool and benchmark improvements"
        normalized = self.intent_engine.run(goal)
        self.assertEqual(normalized.domain, "optimization")
        graph = self.translator.translate(normalized)
        ids = [node.id for node in graph]
        self.assertIn("verify_improvement", ids)
        self.assertIn("benchmark_results", ids)
        self.assertIn("Professional", normalized.preferences)


if __name__ == "__main__":
    unittest.main()
