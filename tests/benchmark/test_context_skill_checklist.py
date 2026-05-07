from __future__ import annotations

import json
from pathlib import Path

from benchmarks import export_answer_checklist


def test_checklist_exports_context_skill_fields(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "benchmarks" / "reports").mkdir(parents=True, exist_ok=True)
    (tmp_path / "benchmarks" / "suites" / "context_skill").mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": "2026-01-01T00:00:00Z",
        "scope": "context_skill",
        "execution_mode": "fake_model",
        "model_provider": "fake",
        "model_backend": "fake",
        "suites": [
            {
                "suite": "context_skill",
                "results": [
                    {
                        "case_id": "context_skill_exec_001",
                        "passed": True,
                        "checks": {"must_call_tools": True},
                        "run_result": {
                            "output_type": "tool_result",
                            "final_answer": "done",
                            "stop_reason": "completed",
                            "tool_calls": [{"name": "repo_reader.read_file"}],
                            "events": [{"type": "context_observation_reused"}, {"type": "skill_tool_denied"}],
                            "loaded_skills": ["summarize_file"],
                            "skill_loads_count": 1,
                            "skills_used": ["summarize_file"],
                            "skill_calls_count": 1,
                            "skill_results": [{"skill_name": "summarize_file", "ok": True}],
                            "summary": {
                                "machine": {
                                    "risks": ["tool_not_allowed_by_skill"],
                                    "tools_used": ["repo_reader.read_file"],
                                    "skills_used": ["summarize_file"],
                                    "context_reuse": True,
                                    "active_task": {"current_phase": "done"},
                                    "handoff_summary": {"current_state": "done"},
                                }
                            },
                        },
                    }
                ],
            }
        ],
    }
    (tmp_path / "benchmarks" / "reports" / "latest.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "benchmarks" / "suites" / "context_skill" / "skill_execution.jsonl").write_text(
        json.dumps({"id": "context_skill_exec_001", "suite": "context_skill", "category": "skill_execution", "input": "总结 README.md"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    assert export_answer_checklist.main() == 0
    rows = json.loads((tmp_path / "temp" / "benchmark_answer_checklist.json").read_text(encoding="utf-8"))["rows"]
    assert rows[0]["skill_observation_reused"] is True
    assert rows[0]["skill_tool_denied_count"] == 1
    md = (tmp_path / "temp" / "benchmark_answer_checklist.md").read_text(encoding="utf-8")
    assert "skill_obs_reused" in md
    assert "skill_tool_denied_count" in md
