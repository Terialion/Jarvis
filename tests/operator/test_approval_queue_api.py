import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from jarvis.core.gateway_state import GatewayState, GatewayReadOnlyAPI

def test_approval_queue_api_shape():
    api = GatewayReadOnlyAPI(GatewayState())
    res = api.operator_approval_queue()
    assert "ok" in res
