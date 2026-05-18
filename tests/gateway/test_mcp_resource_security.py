from src.jarvis.api.server import JarvisApiState, route_request


def test_mcp_resource_security_blocks_unknown_uri():
    status, payload = route_request(
        JarvisApiState(),
        "POST",
        "/api/mcp",
        {"jsonrpc": "2.0", "id": "bad-res", "method": "resources/read", "params": {"uri": "file:///etc/passwd"}},
    )
    assert status == 400
    assert payload["error"]["code"] == -32602
