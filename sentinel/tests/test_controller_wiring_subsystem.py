from sentinel.controller import SentinelController


def test_controller_wires_core_components():
    controller = SentinelController()

    assert controller.tool_registry.has_tool("web_search")
    assert controller.autonomy.planner is controller.planner
    assert controller.autonomy.worker is controller.worker
