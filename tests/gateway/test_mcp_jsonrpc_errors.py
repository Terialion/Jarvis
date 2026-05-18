from src.jarvis.api.server import JarvisApiState, route_request


def test_mcp_unknown_method_returns_jsonrpc_error():
    status, payload = route_request(
        JarvisApiState(),
        "POST",
        "/api/mcp",
        {"jsonrpc": "2.0", "id": "bad-001", "method": "unknown/method", "params": {}},
    )
    assert status == 404
    assert payload["error"]["code"] == -32601
