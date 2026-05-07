from __future__ import annotations

from src.jarvis.api.server import JarvisApiState, route_request


def test_control_surface_status_contract():
    status, payload = route_request(JarvisApiState(), "GET", "/api/control-surface/status")
    assert status == 200
    assert payload["ok"] is True
    data = payload["data"]
    assert data["ok"] is True
    assert data["agent_loop_path"] == "AgentLoop.run_turn"
    assert data["thread_store"] == "available"
    assert data["approval_store"] == "available"
    assert data["browser_automation"] == "out_of_scope"
    assert data["web_fetch_boundary"] == "http_get_readable_extraction_only"
