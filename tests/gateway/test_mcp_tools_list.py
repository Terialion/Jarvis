from src.jarvis.api.server import JarvisApiState, route_request


def test_mcp_tools_list_includes_gateway_tools():
    status, payload = route_request(
        JarvisApiState(), "POST", "/api/mcp", {"jsonrpc": "2.0", "id": "tools", "method": "tools/list", "params": {}}
    )
    assert status == 200
    tools = payload["result"]["tools"]
    names = {t["name"] for t in tools}
    assert "agent.run" in names
    assert "coding.fix" in names
