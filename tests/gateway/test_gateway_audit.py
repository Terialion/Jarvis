from src.jarvis.api.server import JarvisApiState, route_request


def test_gateway_audit_persists_records():
    state = JarvisApiState()
    route_request(state, "POST", "/api/mcp", {"jsonrpc": "2.0", "id": "a1", "method": "tools/list", "params": {}})
    status, payload = route_request(state, "GET", "/api/gateway/audit")
    assert status == 200
    assert isinstance(payload["data"], list)
    assert len(payload["data"]) >= 1
