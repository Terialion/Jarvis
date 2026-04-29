from src.jarvis.api.server import JarvisApiState, route_request


def test_health_api_ok():
    state = JarvisApiState()
    status, payload = route_request(state, "GET", "/api/health")
    assert status == 200
    assert payload["ok"] is True
    assert payload["data"]["status"] == "ok"

