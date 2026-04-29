import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from jarvis.core.gateway_state import GatewayReadOnlyAPI, GatewayState


def test_operator_harness_summary_contains_subagent_field():
    api = GatewayReadOnlyAPI(GatewayState())
    out = api.operator_harness_quality_summary()
    assert out["ok"]
    assert "subagents" in out["data"]
