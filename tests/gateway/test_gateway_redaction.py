from src.jarvis.api.server import JarvisApiState, route_request


def test_gateway_redaction_no_raw_secret_in_response():
    secret = "OPENAI_API_KEY=sk-test-secret"
    status, payload = route_request(
        JarvisApiState(),
        "POST",
        "/api/mcp",
        {
            "jsonrpc": "2.0",
            "id": "redact-1",
            "method": "tools/call",
            "params": {"name": "coding.fix", "arguments": {"path": "src/jarvis/api/server.py", "issue": secret, "apply": True}},
        },
    )
    assert status == 200
    assert secret not in str(payload)
