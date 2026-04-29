from src.jarvis.api.server import JarvisApiState, route_request


def test_operator_summary_contains_skill_counts():
    state = JarvisApiState()
    status_create, create_payload = route_request(
        state,
        "POST",
        "/api/tasks",
        {"input": "Inspect this repo", "mode": "safe", "require_approval": False},
    )
    assert status_create == 200
    task_id = create_payload["data"]["task_id"]

    status, payload = route_request(state, "GET", f"/api/tasks/{task_id}/operator-summary")
    assert status == 200
    data = payload["data"]
    assert "skills" in data
    assert "loaded" in data["skills"]
    assert "selected" in data["skills"]
    assert "quarantined" in data["skills"]
    assert "blocked" in data["skills"]
    assert "approval_required" in data["skills"]
    assert "dry_run" in data["skills"]
    assert "usage_recorded" in data["skills"]
    assert "instruction_sources" in data["skills"]
