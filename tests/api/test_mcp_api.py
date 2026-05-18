from src.jarvis.api.server import JarvisApiState, route_request


def test_mcp_api_endpoints():
    state = JarvisApiState()
    status, payload = route_request(state, "GET", "/api/mcp/capabilities")
    assert status == 200
    assert payload["ok"] is True
    status2, payload2 = route_request(
        state, "POST", "/api/mcp", {"jsonrpc": "2.0", "id": "1", "method": "tools/list", "params": {}}
    )
    assert status2 == 200
    assert "result" in payload2
