from sentinel.controller import SentinelController


def _has_correlation(records, correlation_id: str) -> bool:
    for record in records:
        meta = record.get("metadata", {}) or {}
        value = record.get("value", {}) if isinstance(record.get("value"), dict) else {}
        nested_meta = value.get("metadata", {}) if isinstance(value, dict) else {}
        if meta.get("correlation_id") == correlation_id or value.get("correlation_id") == correlation_id:
            return True
        if isinstance(nested_meta, dict) and nested_meta.get("correlation_id") == correlation_id:
            return True
    return False


def test_full_turn_links_pipeline_artifacts():
    controller = SentinelController()

    controller.conversation_controller.handle_input("run sample task")
    controller.conversation_controller.handle_input("y")

    pipeline_events = controller.memory.recall_recent(limit=1, namespace="pipeline_events")
    assert pipeline_events, "pipeline events should be recorded"
    correlation_id = pipeline_events[0]["value"].get("correlation_id")
    assert correlation_id

    plans = controller.memory.recall_recent(limit=5, namespace="plans")
    execution = controller.memory.recall_recent(limit=10, namespace="execution")
    policy_events = controller.memory.recall_recent(limit=5, namespace="policy_events")

    reflection_records = []
    for namespace in controller.memory.symbolic.list_namespaces():
        if namespace.startswith("reflection"):
            reflection_records.extend(controller.memory.recall_recent(limit=3, namespace=namespace))

    assert _has_correlation(plans, correlation_id), "plan should carry correlation id"
    assert _has_correlation(execution, correlation_id), "execution should carry correlation id"
    assert _has_correlation(policy_events, correlation_id), "policy events should carry correlation id"
    assert _has_correlation(reflection_records, correlation_id), "reflection should carry correlation id"

