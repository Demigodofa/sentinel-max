from sentinel.agent_core.base import ExecutionResult, ExecutionTrace
from sentinel.agent_core.sandbox import Sandbox
from sentinel.execution.execution_controller import ExecutionController, ExecutionMode
from sentinel.execution.approval_gate import ApprovalGate
from sentinel.memory.memory_manager import MemoryManager
from sentinel.planning.adaptive_planner import AdaptivePlanner
from sentinel.policy.policy_engine import PolicyEngine
from sentinel.reflection.reflection_engine import ReflectionEngine
from sentinel.tools.registry import ToolRegistry


class _AutoApprovalGate(ApprovalGate):
    def request_approval(self, description: str) -> None:  # pragma: no cover - trivial override
        self.approved = True
        self.pending_request = None


class _NoOpDialogManager:
    def notify_execution_status(self, status: dict):  # pragma: no cover - trivial stub
        return status


class _StubWorker:
    def __init__(self, tool_registry: ToolRegistry, memory: MemoryManager) -> None:
        self.tool_registry = tool_registry
        self.sandbox = Sandbox()
        self.memory = memory

    def execute_node_real(self, node, context):  # pragma: no cover - deterministic stub
        output = {produced: f"value-{node.id}" for produced in node.produces} if node.produces else "ok"
        return ExecutionResult(node=node, success=True, output=output)


def test_goal_persists_context_plan_and_reflection(tmp_path):
    memory = MemoryManager(storage_dir=tmp_path)
    memory.store_text("seed fact", namespace="notes", metadata={"tags": ["info_query"]})
    policy = PolicyEngine(memory)
    registry = ToolRegistry()
    planner = AdaptivePlanner(registry, memory=memory, policy_engine=policy)

    graph = planner.plan("Review stored memory behavior")

    contexts = memory.query("memory_contexts")
    assert contexts, "expected ranked contexts to be persisted"
    ranked_contexts = [
        c for c in contexts if c.get("metadata", {}).get("type") == "context_window"
    ]
    assert ranked_contexts, "ranked context payload should be stored as structured fact"
    assert any(record.get("value", {}).get("ranked") for record in ranked_contexts), (
        "ranked payload should include ranked contexts"
    )

    planning_traces = memory.query("planning_traces")
    assert planning_traces, "planning traces should be stored"
    assert any(record.get("metadata", {}).get("type") == "planning_trace" for record in planning_traces)

    worker = _StubWorker(registry, memory)
    controller = ExecutionController(
        worker,
        policy,
        _AutoApprovalGate(),
        _NoOpDialogManager(),
        memory,
    )
    trace = controller.request_execution(graph, ExecutionMode.UNTIL_COMPLETE, {})

    execution_logs = memory.query("execution")
    assert execution_logs, "execution summaries and outputs should be logged"
    node_logs = [record for record in execution_logs if record.get("metadata", {}).get("type") == "node_result"]
    assert node_logs, "per-node execution facts should be stored in execution namespace"
    assert any(record.get("value", {}).get("output") for record in node_logs)
    summary_logs = [record for record in execution_logs if record.get("metadata", {}).get("type") == "summary"]
    assert summary_logs, "execution summaries should be persisted as structured facts"
    artifact_logs = [record for record in execution_logs if record.get("metadata", {}).get("type") == "artifacts"]
    assert artifact_logs, "artifacts should be persisted for later recall"
    assert any(isinstance(record.get("value", {}), dict) and record["value"].get("artifacts") for record in artifact_logs)

    reflection_engine = ReflectionEngine(memory, policy_engine=policy)
    reflection = reflection_engine.reflect(trace, goal="Review stored memory behavior")

    reflection_records = memory.query("reflection.operational")
    assert reflection_records, "reflections should be persisted"
    assert any(record.get("metadata", {}).get("type") == "operational" for record in reflection_records)
    assert reflection.get("summary"), "reflection should include a summary"


def test_policy_events_are_structured_and_textual(tmp_path):
    memory = MemoryManager(storage_dir=tmp_path)
    policy = PolicyEngine(memory)

    try:
        policy.check_research_limits("test query", depth=policy.max_research_depth + 1)
    except PermissionError:
        pass

    events = memory.query("policy_events")
    assert events, "policy events should be persisted"
    assert any(
        isinstance(record.get("value"), dict) and record.get("value", {}).get("event") == "block"
        for record in events
    ), "structured policy facts should include the block event payload"
    assert any(record.get("value", {}).get("type") == "text" for record in events), (
        "textual mirrors should be stored alongside structured policy events"
    )
