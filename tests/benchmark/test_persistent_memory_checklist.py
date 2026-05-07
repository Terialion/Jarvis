from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from benchmarks.export_answer_checklist import main as export_main
from benchmarks.run_benchmark import _write_reports, run_suite


def test_persistent_memory_checklist_fields_export(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(Path(__file__).resolve().parents[2])
    suite = run_suite("persistent_memory", model_mode="fake")
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "persistent_memory",
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
        "persistent_memory_metrics": dict(suite.get("metrics") or {}).get("persistent_memory_metrics", {}),
    }
    _write_reports(payload)
    assert export_main() == 0
    text = Path("temp/benchmark_answer_checklist.md").read_text(encoding="utf-8")
    assert "thread_persisted" in text
    assert "persistent_secret_leak_count" in text
