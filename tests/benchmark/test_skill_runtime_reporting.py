from __future__ import annotations

import json
from pathlib import Path

from benchmarks import export_answer_checklist, run_benchmark


def _payload() -> dict:
    return {
        "generated_at": "2026-01-01T00:00:00Z",
        "scope": "jarvis_core",
        "execution_mode": "fake_model",
        "model_provider": "fake",
        "model_name": "fake-agent-v0",
        "model_backend": "fake",
        "suites": [
            {
                "suite": "jarvis_core",
                "total": 1,
                "pass_rate": 1.0,
                "metrics": {
                    "skill_calls_avg": 1.0,
                    "skill_results_count": 1,
                    "context_reuse_rate": 1.0,
                    "active_task_present_rate": 1.0,
                    "handoff_summary_present_rate": 1.0,
                },
                "results": [
                    {
                        "case_id": "jarvis_core_001",
                        "suite": "jarvis_core",
                        "passed": True,
                        "score": 1.0,
                        "checks": {"ok": True},
                        "run_result": {
                            "output_type": "tool_result",
                            "final_answer": "done",
                            "stop_reason": "completed",
                            "tool_calls": [{"name": "repo_reader.read_file"}],
                            "events": [{"type": "skill_call_started", "payload": {"skill_name": "summarize_file"}}],
                            "summary": {
                                "machine": {
                                    "risks": [],
                                    "tools_used": ["repo_reader.read_file"],
                                    "skills_used": ["summarize_file"],
                                    "skill_calls_count": 1,
                                    "context_reuse": True,
                                    "active_task": {"current_phase": "completed"},
                                    "handoff_summary": {"current_state": "done"},
                                }
                            },
                            "available_skills": ["summarize_file"],
                            "loaded_skills": [],
                            "skill_loads_count": 0,
                            "skills_used": ["summarize_file"],
                            "skill_calls_count": 1,
                            "skill_results": [{"skill_name": "summarize_file", "ok": True}],
                        },
                    }
                ],
            }
        ],
    }


def test_benchmark_markdown_includes_skill_runtime_and_context_metrics():
    rendered = run_benchmark._render_markdown(_payload())

    assert "skill_calls_avg" in rendered
    assert "skill_results_count" in rendered
    assert "context_reuse_rate" in rendered
    assert "active_task_present_rate" in rendered
    assert "handoff_summary_present_rate" in rendered
    assert "skills_used" in rendered


def test_answer_checklist_includes_skill_runtime_and_context_fields(tmp_path: Path, monkeypatch):
    payload = _payload()
    monkeypatch.chdir(tmp_path)
    (tmp_path / "benchmarks" / "reports").mkdir(parents=True, exist_ok=True)
    (tmp_path / "benchmarks" / "suites" / "jarvis_core").mkdir(parents=True, exist_ok=True)
    (tmp_path / "benchmarks" / "reports" / "latest.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "benchmarks" / "suites" / "jarvis_core" / "cases.jsonl").write_text(
        json.dumps({"id": "jarvis_core_001", "suite": "jarvis_core", "category": "behavioral", "input": "hi"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    assert export_answer_checklist.main() == 0
    rows = json.loads((tmp_path / "temp" / "benchmark_answer_checklist.json").read_text(encoding="utf-8"))["rows"]
    assert rows[0]["skills_used"] == ["summarize_file"]
    assert rows[0]["skill_calls_count"] == 1
    assert rows[0]["context_reuse"] is True
    assert rows[0]["active_task_present"] is True
    assert rows[0]["handoff_summary_present"] is True
