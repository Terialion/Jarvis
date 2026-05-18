from src.jarvis.api.server import JarvisApiState, route_request


def test_mcp_prompt_safety_unknown_prompt():
    status, payload = route_request(
        JarvisApiState(),
        "POST",
        "/api/mcp",
        {"jsonrpc": "2.0", "id": "p-bad", "method": "prompts/get", "params": {"name": "unknown.prompt", "arguments": {}}},
    )
    assert status == 400
    assert payload["error"]["code"] == -32602
