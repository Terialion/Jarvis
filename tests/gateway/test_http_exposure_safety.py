from src.jarvis.api.server import JarvisApiState, route_request


def test_http_exposure_safety_control_surface_status_declares_boundary():
    status, payload = route_request(JarvisApiState(), "GET", "/api/control-surface/status")
    assert status == 200
    assert payload["data"]["browser_automation"] == "out_of_scope"
    assert payload["data"]["web_fetch_boundary"] == "http_get_readable_extraction_only"
