import unittest
import unittest

from sentinel.memory.memory_manager import MemoryManager
from sentinel.policy.policy_engine import PolicyEngine
from sentinel.research.effect_predictor import ToolEffectPredictorV2
from sentinel.research.research_engine import AutonomousResearchEngine
from sentinel.research.source_ranker import SourceRanker
from sentinel.simulation.sandbox import SimulationSandbox
from sentinel.tools.code_analyzer import CODE_ANALYZER_TOOL
from sentinel.tools.internet_extractor import INTERNET_EXTRACTOR_TOOL
from sentinel.tools.microservice_builder import MICROSERVICE_BUILDER_TOOL
from sentinel.tools.registry import ToolRegistry
from sentinel.tools.web_search import WEB_SEARCH_TOOL


class ResearchEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.memory = MemoryManager()
        self.policy = PolicyEngine(self.memory, max_research_depth=3)
        self.registry = ToolRegistry()
        for tool in [WEB_SEARCH_TOOL, INTERNET_EXTRACTOR_TOOL, CODE_ANALYZER_TOOL, MICROSERVICE_BUILDER_TOOL]:
            if not self.registry.has_tool(tool.name):
                self.registry.register(tool)
        self.sandbox = SimulationSandbox(self.registry, predictor=ToolEffectPredictorV2())
        self.engine = AutonomousResearchEngine(
            self.registry, self.memory, self.policy, simulation_sandbox=self.sandbox
        )

    def test_source_ranker_orders_by_score(self):
        docs = [
            {"source": "a", "content": "relevant content with query", "metadata": {"query": "query"}},
            {"source": "b", "content": "spam ads ads", "metadata": {"query": "query", "tags": ["ads"]}},
        ]
        ranker = SourceRanker("query", memory=self.memory)
        ranked = ranker.rank(docs)
        self.assertGreaterEqual(ranked[0]["score"], ranked[1]["score"])

    def test_research_cycle_populates_namespaces(self):
        models = self.engine.run_research_cycle("sentinel", depth=1)
        self.assertIn("tool_semantics", models)
        self.assertTrue(self.memory.query("research.raw"))
        self.assertTrue(self.memory.query("research.ranked"))
        self.assertTrue(self.memory.query("research.domain"))
        self.assertTrue(self.memory.query("research.tools"))
        self.assertTrue(self.memory.query("research.models"))
        self.assertTrue(self.memory.query("research.predictor_updates"))

    def test_predictor_updates_semantics(self):
        predictor = ToolEffectPredictorV2()
        predictor.update_model({"demo": {"outputs": {"result": "ok"}, "failure_likelihood": 0.2}})
        prediction = predictor.predict("demo", {"path": "file.txt"})
        self.assertIn("file.txt", prediction["vfs_writes"])
        self.assertEqual(prediction["outputs"].get("result"), "ok")
        self.assertLess(prediction["failure_likelihood"], 1)

    def test_policy_blocks_excessive_research_depth(self):
        with self.assertRaises(PermissionError):
            self.policy.check_research_limits("test", depth=5)


if __name__ == "__main__":
    unittest.main()
