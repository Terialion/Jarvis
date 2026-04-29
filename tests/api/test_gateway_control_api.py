from src.jarvis.api.server import JarvisApiState, route_request


def test_gateway_control_endpoints_exist():
    state = JarvisApiState()
    for path in [
        "/api/gateway/status",
        "/api/channels",
        "/api/nodes",
        "/api/skills",
        "/api/logs",
        "/api/resources",
    ]:
        status, payload = route_request(state, "GET", path)
        assert status == 200
        assert payload["ok"] is True

