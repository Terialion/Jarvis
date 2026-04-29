from src.jarvis.api.server import JarvisApiState, route_request


def test_skill_selection_writes_replay_and_evidence():
    state = JarvisApiState()
    status, created = route_request(
        state,
        "POST",
        "/api/tasks",
        {"input": "Inspect this repo structure with repo skill", "mode": "safe", "require_approval": False},
    )
    assert status == 200
    task_id = created["data"]["task_id"]

    status_events, payload_events = route_request(state, "GET", f"/api/tasks/{task_id}/events")
    assert status_events == 200
    event_types = [event["type"] for event in payload_events["data"]]
    assert "skill.registry.loaded" in event_types
    assert "skill.selected" in event_types

    status_evidence, payload_evidence = route_request(state, "GET", f"/api/tasks/{task_id}/evidence")
    assert status_evidence == 200
    kinds = [item["kind"] for item in payload_evidence["data"]["artifacts"]]
    assert "skill_selection" in kinds

