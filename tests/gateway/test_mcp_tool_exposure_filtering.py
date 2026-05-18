from src.jarvis.api.server import JarvisApiState, route_request


def test_mcp_tool_exposure_filtering_hides_raw_tools():
    status, payload = route_request(
        JarvisApiState(), "POST", "/api/mcp", {"jsonrpc": "2.0", "id": "tools", "method": "tools/list", "params": {}}
    )
    assert status == 200
    names = {t["name"] for t in payload["result"]["tools"]}
    assert "shell.run" not in names
    assert "file.apply_patch" not in names
