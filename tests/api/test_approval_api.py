from src.jarvis.api.server import JarvisApiState, route_request


def test_approval_list_and_approve():
    state = JarvisApiState()
    _, created = route_request(state, "POST", "/api/tasks", {"input": "x", "require_approval": True})
    task_id = created["data"]["task_id"]

    status_list, payload_list = route_request(state, "GET", "/api/approvals")
    assert status_list == 200
    approvals = payload_list["data"]
    assert approvals
    approval_id = approvals[-1]["approval_id"]

    status_ok, payload_ok = route_request(state, "POST", f"/api/approvals/{approval_id}/approve")
    assert status_ok == 200
    assert payload_ok["data"]["status"] == "approved"

    status_events, payload_events = route_request(state, "GET", f"/api/tasks/{task_id}/events")
    assert status_events == 200
    assert any(e["type"] == "approval.resolved" for e in payload_events["data"])

