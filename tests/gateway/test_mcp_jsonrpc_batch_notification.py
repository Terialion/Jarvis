from src.jarvis.api.server import JarvisApiState, route_request


def test_mcp_batch_and_notification():
    status, payload = route_request(
        JarvisApiState(),
        "POST",
        "/api/mcp",
        [
            {"jsonrpc": "2.0", "id": "one", "method": "tools/list", "params": {}},
            {"jsonrpc": "2.0", "method": "tools/list", "params": {}},
        ],
    )
    assert status == 200
    assert isinstance(payload, list)
    assert payload[0]["id"] == "one"
