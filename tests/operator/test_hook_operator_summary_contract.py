from jarvis.core.gateway_state import GatewayReadOnlyAPI, GatewayState


def test_operator_summary_contains_hook_counters():
    api = GatewayReadOnlyAPI(GatewayState())
    hooks = api.operator_harness_quality_summary()["data"]["hooks"]
    for k in ["fired_count", "failed_count", "blocked_count"]:
        assert k in hooks

