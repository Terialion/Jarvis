from src.jarvis.api.server import JarvisApiState, route_request


def test_gateway_run_route_works():
    status, payload = route_request(JarvisApiState(), "POST", "/api/gateway/run", {"input": "Say hi", "channel": "api"})
    assert status == 200
    assert payload["ok"] is True
    assert payload["data"]["request_id"]
