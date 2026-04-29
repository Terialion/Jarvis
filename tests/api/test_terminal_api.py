from src.jarvis.api.server import JarvisApiState, route_request


def test_terminal_session_is_safe_by_default():
    state = JarvisApiState()
    status, payload = route_request(state, "POST", "/api/terminal/sessions", {"mode": "safe"})
    assert status == 200
    data = payload["data"]
    assert data["session_id"].startswith("term_")
    assert data["safe_use"]["command_execution_enabled"] is False


def test_terminal_input_is_blocked_in_safe_mode():
    state = JarvisApiState()
    _, created = route_request(state, "POST", "/api/terminal/sessions", {"mode": "safe"})
    session_id = created["data"]["session_id"]
    status, payload = route_request(
        state,
        "POST",
        f"/api/terminal/sessions/{session_id}/input",
        {"input": "rm -rf /"},
    )
    assert status == 200
    assert payload["data"]["accepted"] is False
