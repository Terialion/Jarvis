from src.jarvis.api.server import JarvisApiState, route_request


def test_create_task_and_readback():
    state = JarvisApiState()
    status, payload = route_request(
        state,
        "POST",
        "/api/tasks",
        {
            "input": "Analyze this repo and suggest next steps.",
            "mode": "safe",
            "allow_code_changes": False,
            "max_commands": 3,
            "max_files_changed": 0,
            "require_approval": True,
        },
    )
    assert status == 200
    task_id = payload["data"]["task_id"]
    assert task_id.startswith("task_")

    status2, payload2 = route_request(state, "GET", f"/api/tasks/{task_id}")
    assert status2 == 200
    assert payload2["data"]["task_id"] == task_id

