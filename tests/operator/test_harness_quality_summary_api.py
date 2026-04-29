import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from jarvis.core.gateway_state import GatewayState, GatewayReadOnlyAPI

def test_harness_quality_summary_api():
    api = GatewayReadOnlyAPI(GatewayState())
    res = api.operator_harness_quality_summary()
    assert res["ok"]
    assert "route" in res["data"]
