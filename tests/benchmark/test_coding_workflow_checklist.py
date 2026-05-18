from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from benchmarks.export_answer_checklist import main as export_main
from benchmarks.run_benchmark import _write_reports, run_suite


def test_coding-workflow_checklist_fields_export(monkeypatch):
    monkeypatch.chdir(Path(__file__).resolve().parents[2])
    suite = run_suite("coding-workflow", model_mode="fake")
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "coding-workflow",
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
        "coding-workflow_metrics": dict(suite.get("metrics") or {}).get("coding-workflow_metrics", {}),
    }
    _write_reports(payload)
    assert export_main() == 0
    text = Path("temp/benchmark_answer_checklist.md").read_text(encoding="utf-8")
    assert "coding_task_created" in text
    assert "patch_plan_created" in text
    assert "coding_secret_leak_count" in text
