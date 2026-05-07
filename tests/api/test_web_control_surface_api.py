from __future__ import annotations

from src.jarvis.api.server import JarvisApiState, route_request


def test_agent_run_returns_timeline_for_control_surface():
    status, payload = route_request(
        JarvisApiState(),
        "POST",
        "/api/agent/run",
        {"text": "Read README.md and summarize it.", "model_mode": "fake"},
    )
    assert status == 200
    assert "result" in payload
    result = payload["result"]
    assert "timeline" in result
    assert isinstance(result["timeline"]["items"], list)
    assert "tool_calls_count" in result
