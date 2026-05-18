from src.jarvis.gateway.schema import GatewayRequest, McpJsonRpcRequest


def test_gateway_schema_dataclasses_construct():
    req = GatewayRequest(request_id="r1", channel="mock_mcp", user_id=None, text="hello")
    assert req.request_id == "r1"
    mcp = McpJsonRpcRequest(jsonrpc="2.0", id="1", method="initialize", params={})
    assert mcp.method == "initialize"
