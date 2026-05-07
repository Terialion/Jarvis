from src.jarvis.api.server import JarvisApiState, route_request
from src.jarvis.core.policy import get_approval_store


def test_approval_list_and_approve():
    get_approval_store().reset()
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


def test_permissions_endpoint_and_global_approval_api():
    store = get_approval_store()
    store.reset()
    request = store.create_request(
        tool_name="command_runner.run",
        arguments_preview={"command": "python -V"},
        risk_level="high",
        reason="api test",
    )
    state = JarvisApiState()
    status_perm, payload_perm = route_request(state, "GET", "/api/permissions")
    assert status_perm == 200
    assert payload_perm["ok"] is True
    assert payload_perm["data"]["profile"]

    status_list, payload_list = route_request(state, "GET", "/api/approvals")
    assert status_list == 200
    assert any(row["approval_id"] == request.approval_id for row in payload_list["data"])

    status_deny, payload_deny = route_request(state, "POST", f"/api/approvals/{request.approval_id}/deny")
    assert status_deny == 200
    assert payload_deny["data"]["status"] == "denied"

