from benchmarks.run_benchmark import run_suite


def test_gateway_mcp_metrics_present():
    result = run_suite("gateway_mcp", model_mode="fake")
    metrics = dict(result.get("metrics") or {}).get("gateway_mcp_metrics") or {}
    assert metrics["gateway_status_success_rate"] == 1.0
    assert metrics["mcp_initialize_success_rate"] == 1.0
    assert metrics["gateway_secret_leak_count"] == 0
    assert metrics["mcp_second_agent_loop_violation_count"] == 0
