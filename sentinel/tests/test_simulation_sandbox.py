import unittest

from sentinel.agent_core.base import Tool
from sentinel.planning.task_graph import TaskGraph, TaskNode
from sentinel.simulation.sandbox import (
    BenchmarkFacade,
    SimulationSandbox,
    ToolEffectPredictor,
    VirtualFileSystem,
)
from sentinel.tools.registry import ToolRegistry
from sentinel.tools.tool_schema import ToolSchema


class DummyTool(Tool):
    def __init__(self, name: str, required_path: bool = False, description: str = ""):
        super().__init__(name=name, description=description or name)
        self.schema = ToolSchema(
            name=name,
            version="0.0.1",
            description=description or name,
            input_schema={
                "path": {"type": "string", "required": required_path},
                "payload": {"type": "string", "required": False},
            },
            output_schema={"artifact": "string"},
            permissions=["fs"],
            deterministic=True,
        )

    def execute(self, **kwargs):  # pragma: no cover - simulation only
        return kwargs


class TestSimulationSandbox(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ToolRegistry()
        self.registry.register(DummyTool("file_writer", required_path=True, description="create a file"))
        self.registry.register(DummyTool("scraper", description="pull web data"))
        self.registry.register(DummyTool("microservice_builder", description="build service"))
        self.sandbox = SimulationSandbox(self.registry)

    def test_virtual_fs_overlay(self):
        vfs = VirtualFileSystem()
        vfs.write("/tmp/demo.txt", "synthetic content")
        self.assertTrue(vfs.exists("/tmp/demo.txt"))
        self.assertEqual(vfs.read("/tmp/demo.txt"), "synthetic content")
        self.assertIn("/tmp/demo.txt", vfs.list())

    def test_simulate_tool_creating_file(self):
        result = self.sandbox.simulate_tool_call(
            "file_writer",
            {"path": "/virtual/output.txt", "payload": "hello"},
            world_model=None,
        )
        self.assertTrue(result.success)
        self.assertIn("/virtual/output.txt", result.predicted_vfs_changes)
        self.assertTrue(self.sandbox.vfs.exists("/virtual/output.txt"))

    def test_simulate_scraper_and_microservice(self):
        scraper = self.sandbox.simulate_tool_call("scraper", {"path": "data.json"}, world_model=None)
        builder = self.sandbox.simulate_tool_call(
            "microservice_builder", {"path": "service.py", "payload": "api"}, world_model=None
        )
        self.assertTrue(scraper.success)
        self.assertTrue(builder.success)
        self.assertIn("data.json", self.sandbox.vfs.list())
        self.assertIn("service.py", self.sandbox.vfs.list())

    def test_simulate_multiple_dag_nodes(self):
        graph = TaskGraph(
            [
                TaskNode(
                    id="fetch_data",
                    description="Fetch dataset",
                    tool="scraper",
                    args={"path": "dataset.json"},
                    produces=["raw_data"],
                ),
                TaskNode(
                    id="build_service",
                    description="Build microservice",
                    tool="microservice_builder",
                    args={"path": "service.py"},
                    requires=["raw_data"],
                    produces=["service_artifact"],
                ),
            ]
        )
        results = self.sandbox.simulate_taskgraph(graph, world_model=None)
        self.assertSetEqual(set(results.keys()), {"fetch_data", "build_service"})
        self.assertTrue(all(result.success for result in results.values()))

    def test_missing_parameters_are_flagged(self):
        result = self.sandbox.simulate_tool_call("file_writer", {"payload": "no path"}, world_model=None)
        self.assertFalse(result.success)
        self.assertTrue(result.warnings)

    def test_benchmark_facade_optimization_signals(self):
        predictor = ToolEffectPredictor()
        benchmark = BenchmarkFacade()
        tool = DummyTool("optimizer")
        estimate = benchmark.estimate_performance(tool, {"payload": "x" * 200})
        predictions = predictor.predict(tool, {"path": "opt.txt"}, world_model=None)
        self.assertLess(estimate["relative_speed"], 10)
        self.assertIn("opt.txt", predictions["vfs_writes"])


if __name__ == "__main__":
    unittest.main()
