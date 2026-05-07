from __future__ import annotations

import json
from pathlib import Path

from benchmarks import export_answer_checklist, run_benchmark


def test_skill_lifecycle_checklist_fields_present(tmp_path: Path, monkeypatch):
    payload = {
        "generated_at": "2026-01-01T00:00:00Z",
        "scope": "skill_lifecycle",
        "execution_mode": "fake_model",
        "model_provider": "fake",
        "model_name": "fake-agent-v0",
        "model_backend": "fake",
        "suites": [
            {
                "suite": "skill_lifecycle",
                "total": 1,
                "pass_rate": 1.0,
                "metrics": {},
                "results": [
                    {
                        "case_id": "skill_lifecycle_install_001",
                        "suite": "skill_lifecycle",
                        "passed": True,
                        "score": 1.0,
                        "checks": {"ok": True},
                        "run_result": {
                            "output_type": "answer",
                            "final_answer": "done",
                            "stop_reason": "completed",
                            "tool_calls": [],
                            "events": [],
                            "summary": {"machine": {"skill_installed": True, "skill_enabled": False, "skill_quarantined": False}},
                        },
                    }
                ],
            }
        ],
    }
    rendered = run_benchmark._render_markdown(payload)
    assert "## Skill Lifecycle Metrics" in rendered

    monkeypatch.chdir(tmp_path)
    (tmp_path / "benchmarks" / "reports").mkdir(parents=True, exist_ok=True)
    (tmp_path / "benchmarks" / "suites" / "skill_lifecycle").mkdir(parents=True, exist_ok=True)
    (tmp_path / "benchmarks" / "reports" / "latest.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "benchmarks" / "suites" / "skill_lifecycle" / "cases.jsonl").write_text(
        json.dumps({"id": "skill_lifecycle_install_001", "suite": "skill_lifecycle", "category": "install", "input": "x"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    assert export_answer_checklist.main() == 0
    checklist_json = json.loads((tmp_path / "temp" / "benchmark_answer_checklist.json").read_text(encoding="utf-8"))
    row = checklist_json["rows"][0]
    assert "skill_installed" in row
    assert "skill_quarantined" in row
