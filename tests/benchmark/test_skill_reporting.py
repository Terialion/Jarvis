from __future__ import annotations

import json
from pathlib import Path

from benchmarks import export_answer_checklist, run_benchmark


def test_benchmark_markdown_and_checklist_include_skill_fields(tmp_path: Path, monkeypatch):
    payload = {
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
                "metrics": {},
                "results": [
                    {
                        "case_id": "jarvis_core_001",
                        "suite": "jarvis_core",
                        "passed": True,
                        "score": 1.0,
                        "checks": {"ok": True},
                        "run_result": {
                            "output_type": "answer",
                            "final_answer": "done",
                            "stop_reason": "completed",
                            "tool_calls": [],
                            "events": [{"type": "turn_started", "payload": {"text": "hi"}}],
                            "summary": {"machine": {"risks": [], "tools_used": []}},
                            "available_skills": ["repo_overview", "summarize_file"],
                            "loaded_skills": ["summarize_file"],
                            "skill_loads_count": 1,
                        },
                    }
                ],
            }
        ],
    }
    rendered = run_benchmark._render_markdown(payload)
    assert "skill_loads_count" in rendered
    assert "loaded_skills" in rendered

    monkeypatch.chdir(tmp_path)
    (tmp_path / "benchmarks" / "reports").mkdir(parents=True, exist_ok=True)
    (tmp_path / "benchmarks" / "suites" / "jarvis_core").mkdir(parents=True, exist_ok=True)
    (tmp_path / "benchmarks" / "reports" / "latest.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "benchmarks" / "suites" / "jarvis_core" / "cases.jsonl").write_text(
        json.dumps({"id": "jarvis_core_001", "suite": "jarvis_core", "category": "behavioral", "input": "hi"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    assert export_answer_checklist.main() == 0
    checklist = (tmp_path / "temp" / "benchmark_answer_checklist.md").read_text(encoding="utf-8")
    checklist_json = json.loads((tmp_path / "temp" / "benchmark_answer_checklist.json").read_text(encoding="utf-8"))
    assert "skill_loads_count" in checklist
    assert checklist_json["rows"][0]["loaded_skills"] == ["summarize_file"]

