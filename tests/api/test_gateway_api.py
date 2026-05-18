from src.jarvis.api.server import JarvisApiState, route_request


def test_gateway_api_endpoints():
    state = JarvisApiState()
    for path in ("/api/gateway/status", "/api/gateway/channels", "/api/gateway/audit"):
        status, payload = route_request(state, "GET", path)
        assert status == 200
        assert payload["ok"] is True
