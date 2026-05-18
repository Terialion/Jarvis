from benchmarks.run_benchmark import run_suite


def test_gateway_mcp_suite_runs_fake():
    result = run_suite("gateway_mcp", model_mode="fake")
    assert result["suite"] == "gateway_mcp"
    assert result["total"] >= 1
    assert result["pass_rate"] == 1.0
