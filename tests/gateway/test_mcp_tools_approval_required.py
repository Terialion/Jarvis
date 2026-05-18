from src.jarvis.api.server import JarvisApiState, route_request


def test_mcp_mutating_tool_requires_approval():
    status, payload = route_request(
        JarvisApiState(),
        "POST",
        "/api/mcp",
        {
            "jsonrpc": "2.0",
            "id": "call-approval",
            "method": "tools/call",
            "params": {"name": "coding.fix", "arguments": {"path": "src/jarvis/api/server.py", "apply": True}},
        },
    )
    assert status == 200
    structured = payload["result"]["structuredContent"]
    assert structured["status"] == "approval_required"
    assert structured["approval_id"]
