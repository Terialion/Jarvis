from datetime import datetime, timezone
from pathlib import Path

from benchmarks.export_answer_checklist import main as export_main
from benchmarks.run_benchmark import _write_reports, run_suite


def test_gateway_mcp_checklist_export():
    suite = run_suite("gateway_mcp", model_mode="fake")
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "gateway_mcp",
        "execution_mode": "fake_model",
        "model_provider": "fake",
        "model_name": "fake-agent-v0",
        "model_backend": "fake",
        "suites": [suite],
        "behavior_metrics": {},
        "context_skill_metrics": {},
        "web_research_metrics": {},
        "web_research_smoke_metrics": {},
        "skill_lifecycle_metrics": {},
        "permissions_metrics": {},
        "persistent_memory_metrics": {},
        "control_surface_metrics": {},
        "coding-workflow_metrics": {},
        "gateway_mcp_metrics": dict(suite.get("metrics") or {}).get("gateway_mcp_metrics", {}),
    }
    _write_reports(payload)
    assert export_main() == 0
    text = Path("temp/benchmark_answer_checklist.md").read_text(encoding="utf-8")
    assert "gateway_mcp" in text
