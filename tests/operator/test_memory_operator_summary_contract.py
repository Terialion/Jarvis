from jarvis.core.gateway_state import GatewayReadOnlyAPI, GatewayState


def test_memory_operator_summary_contract():
    data = GatewayReadOnlyAPI(GatewayState()).operator_harness_quality_summary()["data"]["memory"]
    for key in ["memory_used", "memory_written", "memory_rejected", "memory_redacted"]:
        assert key in data

