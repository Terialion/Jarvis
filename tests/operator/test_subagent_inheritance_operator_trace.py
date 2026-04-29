from jarvis.core.gateway_state import GatewayReadOnlyAPI, GatewayState


def test_operator_summary_contains_subagent_section():
    api = GatewayReadOnlyAPI(GatewayState())
    resp = api.operator_harness_quality_summary()
    assert resp["ok"] is True
    assert "subagents" in (resp["data"] or {})

