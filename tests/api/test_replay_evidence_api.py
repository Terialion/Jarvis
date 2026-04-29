from src.jarvis.api.server import JarvisApiState, route_request


def test_replay_and_evidence_api():
    state = JarvisApiState()
    _, created = route_request(state, "POST", "/api/tasks", {"input": "x"})
    task_id = created["data"]["task_id"]

    status_replay, payload_replay = route_request(state, "GET", f"/api/tasks/{task_id}/replay")
    assert status_replay == 200
    assert isinstance(payload_replay["data"], list)

    status_ev, payload_ev = route_request(state, "GET", f"/api/tasks/{task_id}/evidence")
    assert status_ev == 200
    assert payload_ev["data"]["task_id"] == task_id

