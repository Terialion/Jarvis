from src.jarvis.api.server import JarvisApiState, route_request


def test_mcp_run_convenience_endpoint():
    status, payload = route_request(
        JarvisApiState(),
        "POST",
        "/api/mcp/run",
        {"jsonrpc": "2.0", "id": "tools", "method": "tools/list", "params": {}},
    )
    assert status == 200
    assert payload["ok"] is True
    assert "canonical MCP wire format" in payload["data"]["note"]
