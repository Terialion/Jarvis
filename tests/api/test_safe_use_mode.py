from src.jarvis.api.server import JarvisApiState, route_request


def test_settings_effective_safe_mode_default():
    state = JarvisApiState()
    status, payload = route_request(state, "GET", "/api/settings/effective")
    assert status == 200
    assert payload["data"]["mode"] == "workspace_write"

