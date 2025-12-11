from sentinel.policy.policy_engine import PolicyEngine, PolicyViolation


def test_policy_project_limits():
    policy = PolicyEngine(max_goals=2)
    data = {"goals": [{"id": "g1"}, {"id": "g2"}, {"id": "g3"}]}
    try:
        policy.check_project_limits(data)
        assert False, "Should have raised policy violation"
    except PolicyViolation:
        assert True
