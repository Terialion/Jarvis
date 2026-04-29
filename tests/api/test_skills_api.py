from src.jarvis.api.server import JarvisApiState, route_request


def test_skills_api_returns_skill_records():
    state = JarvisApiState()
    status, payload = route_request(state, "GET", "/api/skills")
    assert status == 200
    assert payload["ok"] is True
    data = payload["data"]
    assert "skills" in data
    assert isinstance(data["skills"], list)
    if data["skills"]:
        first = data["skills"][0]
        for key in ("id", "name", "status", "trust", "quarantine", "source"):
            assert key in first

