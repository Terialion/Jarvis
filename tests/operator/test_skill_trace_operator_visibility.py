from src.jarvis.api.server import JarvisApiState, route_request


def test_skill_trace_events_visible_in_task_events_and_operator_summary():
    state = JarvisApiState()
    status_create, create_payload = route_request(
        state,
        "POST",
        "/api/tasks",
        {"input": "Choose the best skill for inspecting this repo. Do not modify files.", "mode": "safe", "require_approval": False},
    )
    assert status_create == 200
    task_id = create_payload["data"]["task_id"]

    status_events, events_payload = route_request(state, "GET", f"/api/tasks/{task_id}/events")
    assert status_events == 200
    events = list(events_payload["data"])
    event_types = [str(e.get("type")) for e in events]
    assert "skill.registry.loaded" in event_types
    assert "skill.routing.context_loaded" in event_types
    assert "skill.usage.recorded" in event_types

    status_summary, summary_payload = route_request(state, "GET", f"/api/tasks/{task_id}/operator-summary")
    assert status_summary == 200
    skills = summary_payload["data"]["skills"]
    assert "usage_recorded" in skills
    assert "instruction_sources" in skills
