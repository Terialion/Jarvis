import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from jarvis.core.gateway_state import GatewayState, GatewayReadOnlyAPI

def test_patch_review_api_missing_run():
    api = GatewayReadOnlyAPI(GatewayState())
    res = api.operator_patch_review("missing")
    assert res["ok"] is False
