from src.jarvis.api.server import JarvisApiState, route_request


def test_mcp_prompts_list_and_get():
    state = JarvisApiState()
    s1, p1 = route_request(state, "POST", "/api/mcp", {"jsonrpc": "2.0", "id": "p1", "method": "prompts/list", "params": {}})
    assert s1 == 200
    assert p1["result"]["prompts"]
    s2, p2 = route_request(
        state,
        "POST",
        "/api/mcp",
        {
            "jsonrpc": "2.0",
            "id": "p2",
            "method": "prompts/get",
            "params": {"name": "jarvis.coding.review", "arguments": {"path": "src/jarvis/agent/loop.py"}},
        },
    )
    assert s2 == 200
    assert p2["result"]["messages"]
