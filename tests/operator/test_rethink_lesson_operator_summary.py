from jarvis.core.gateway_state import GatewayReadOnlyAPI, GatewayState


def test_operator_summary_contains_rethink_section():
    api = GatewayReadOnlyAPI(GatewayState())
    data = api.operator_harness_quality_summary()["data"]
    assert "rethink" in data

