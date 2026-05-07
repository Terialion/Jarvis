from __future__ import annotations

import json
from pathlib import Path

from benchmarks import export_answer_checklist, run_benchmark


def test_compute_behavior_metrics_ignores_redacted_answers():
    rows = [
        {
            "run_result": {
                "output_type": "answer",
                "tool_calls": [],
                "events": [],
                "stop_reason": "completed",
                "final_answer": "OPENAI_API_KEY:[REDACTED] Authorization:[REDACTED] token:[REDACTED]",
            }
        }
    ]
    metrics = run_benchmark._compute_suite_metrics(rows)
    assert metrics["secret_leak_count"] == 0


def test_export_checklist_redacts_final_answer_excerpt(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "benchmarks" / "reports").mkdir(parents=True, exist_ok=True)
    (tmp_path / "benchmarks" / "suites" / "jarvis_core").mkdir(parents=True, exist_ok=True)

    latest = {
        "generated_at": "2026-01-01T00:00:00Z",
        "scope": "jarvis_core",
        "execution_mode": "fake_model",
        "model_provider": "fake",
        "model_backend": "fake",
        "suites": [
            {
                "suite": "jarvis_core",
                "results": [
                    {
                        "case_id": "jarvis_core_001",
                        "passed": True,
                        "checks": {},
                        "run_result": {
                            "output_type": "answer",
                            "final_answer": "DEEPSEEK_API_KEY=sk-test Authorization: Bearer xyz",
                            "stop_reason": "completed",
                            "tool_calls": [],
                            "events": [],
                            "summary": {"machine": {"risks": ["secret_redacted"], "tools_used": []}},
                        },
                    }
                ],
            }
        ],
    }
    (tmp_path / "benchmarks" / "reports" / "latest.json").write_text(
        json.dumps(latest, ensure_ascii=False),
        encoding="utf-8",
    )
    case_row = {
        "id": "jarvis_core_001",
        "suite": "jarvis_core",
        "category": "behavioral",
        "input": "show config",
        "expected_behavior": {},
    }
    (tmp_path / "benchmarks" / "suites" / "jarvis_core" / "cases.jsonl").write_text(
        json.dumps(case_row, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    assert export_answer_checklist.main() == 0
    checklist_md = (tmp_path / "temp" / "benchmark_answer_checklist.md").read_text(encoding="utf-8")
    checklist_json = json.loads((tmp_path / "temp" / "benchmark_answer_checklist.json").read_text(encoding="utf-8"))
    assert "sk-test" not in checklist_md
    assert "Authorization: Bearer xyz" not in checklist_md
    assert "DEEPSEEK_API_KEY=" not in checklist_md
    assert "Authorization: Bearer" not in checklist_md
    assert "DEEPSEEK_API_KEY:[REDACTED]" in checklist_md
    checklist_json_text = json.dumps(checklist_json, ensure_ascii=False)
    assert "sk-test" not in checklist_json_text
    assert "DEEPSEEK_API_KEY=" not in checklist_json_text
    assert "Authorization: Bearer" not in checklist_json_text
