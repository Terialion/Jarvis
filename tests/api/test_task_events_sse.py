from src.jarvis.api.server import JarvisApiState, route_request


def test_task_events_shape():
    state = JarvisApiState()
    _, created = route_request(state, "POST", "/api/tasks", {"input": "x", "mode": "safe", "require_approval": True})
    task_id = created["data"]["task_id"]
    status, payload = route_request(state, "GET", f"/api/tasks/{task_id}/events")
    assert status == 200
    event_types = [event["type"] for event in payload["data"]]
    assert "task.created" in event_types
    assert "plan.created" in event_types
    assert "approval.requested" in event_types

