from src.jarvis.api.server import JarvisApiState, route_request


def test_mcp_protocol_version_rejected_if_unsupported():
    status, payload = route_request(
        JarvisApiState(),
        "POST",
        "/api/mcp",
        {"jsonrpc": "2.0", "id": "init-bad", "method": "initialize", "params": {"protocolVersion": "2024-01-01"}},
    )
    assert status == 400
    assert payload["error"]["code"] == -32602
