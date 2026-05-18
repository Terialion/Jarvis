from src.jarvis.api.server import JarvisApiState, route_request


def test_gateway_permissions_enforced_for_mcp_mutation():
    status, payload = route_request(
        JarvisApiState(),
        "POST",
        "/api/mcp",
        {
            "jsonrpc": "2.0",
            "id": "perm-1",
            "method": "tools/call",
            "params": {"name": "coding.fix", "arguments": {"path": "src/jarvis/api/server.py", "apply": True}},
        },
    )
    assert status == 200
    assert payload["result"]["structuredContent"]["status"] == "approval_required"
