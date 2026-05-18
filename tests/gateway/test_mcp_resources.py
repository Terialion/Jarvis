from src.jarvis.api.server import JarvisApiState, route_request


def test_mcp_resources_list_and_read():
    state = JarvisApiState()
    s1, p1 = route_request(state, "POST", "/api/mcp", {"jsonrpc": "2.0", "id": "r1", "method": "resources/list", "params": {}})
    assert s1 == 200
    assert p1["result"]["resources"]
    s2, p2 = route_request(
        state,
        "POST",
        "/api/mcp",
        {"jsonrpc": "2.0", "id": "r2", "method": "resources/read", "params": {"uri": "jarvis://benchmarks/latest"}},
    )
    assert s2 == 200
    assert p2["result"]["contents"]
