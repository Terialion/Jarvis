from src.jarvis.api.server import JarvisApiState, route_request


def test_operator_summary_api():
    state = JarvisApiState()
    _, created = route_request(state, "POST", "/api/tasks", {"input": "x"})
    task_id = created["data"]["task_id"]
    status, payload = route_request(state, "GET", f"/api/tasks/{task_id}/operator-summary")
    assert status == 200
    summary = payload["data"]
    assert "route_summary" in summary
    assert "risk_summary" in summary
    assert "hooks_summary" in summary
    assert "memory_summary" in summary

