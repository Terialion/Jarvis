from src.jarvis.api.server import JarvisApiState, route_request


def test_mcp_initialize():
    status, payload = route_request(
        JarvisApiState(),
        "POST",
        "/api/mcp",
        {
            "jsonrpc": "2.0",
            "id": "init-001",
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "clientInfo": {"name": "test", "version": "0.1"}},
        },
    )
    assert status == 200
    assert payload["result"]["protocolVersion"] == "2025-06-18"
