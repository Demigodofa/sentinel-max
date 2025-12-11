import tempfile
import unittest

from sentinel.memory.memory_manager import MemoryManager
from sentinel.world.model import WorldModel


class TestWorldModel(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.memory = MemoryManager(storage_dir=self.tempdir.name)
        self.world_model = WorldModel(self.memory)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_domain_detection_samples(self):
        expectations = {
            "build microservice": "multi-service",
            "optimize the scraper tool": "optimization",
            "pull prices from this website": "web tasks",
            "design a data pipeline": "pipelines",
        }
        for goal, expected_domain in expectations.items():
            domain = self.world_model.get_domain(goal)
            self.assertEqual(expected_domain, domain.name)
        optimization_capabilities = self.world_model.list_capabilities("optimization")
        self.assertIn("coding", optimization_capabilities)

    def test_capability_listing_and_resources(self):
        coding_caps = self.world_model.list_capabilities("coding")
        self.assertIn("analysis", coding_caps)
        resources = self.world_model.predict_required_resources("design a data pipeline")
        resource_names = [resource.name for resource in resources]
        self.assertIn("pipeline", resource_names)
        self.assertIn("data_source", resource_names)

    def test_dependency_prediction(self):
        dependencies = self.world_model.predict_dependencies("design a data pipeline")
        requires = dependencies.get("requires", {})
        self.assertIn("pipeline", requires)
        self.assertIn("data_source", requires.get("pipeline", set()))
        coding_dependencies = self.world_model.predict_dependencies("optimize the scraper tool")
        coding_requires = coding_dependencies.get("requires", {})
        self.assertIn("code_artifact", coding_requires)
        self.assertIn("file_resource", coding_requires.get("code_artifact", set()))


if __name__ == "__main__":
    unittest.main()
