from src.jarvis.api.server import JarvisApiState, route_request


def test_mcp_tools_call_agent_run():
    status, payload = route_request(
        JarvisApiState(),
        "POST",
        "/api/mcp",
        {
            "jsonrpc": "2.0",
            "id": "call-001",
            "method": "tools/call",
            "params": {"name": "agent.run", "arguments": {"input": "hello", "thread_id": "t1"}},
        },
    )
    assert status == 200
    assert payload["result"]["isError"] is False
