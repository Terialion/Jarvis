from __future__ import annotations

from src.jarvis.api.server import JarvisApiState, route_request


def test_benchmark_dashboard_reads_latest_report():
    status, payload = route_request(JarvisApiState(), "GET", "/api/benchmarks/latest")
    assert status == 200
    assert payload["ok"] is True
    assert "generated_at" in payload["data"]
