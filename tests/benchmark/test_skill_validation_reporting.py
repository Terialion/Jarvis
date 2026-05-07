from __future__ import annotations

from benchmarks import run_benchmark


def test_behavior_metrics_include_available_skills_count():
    rows = [
        {
            "run_result": {
                "output_type": "answer",
                "tool_calls": [],
                "events": [],
                "stop_reason": "completed",
                "final_answer": "ok",
                "available_skills": ["repo_overview", "skill_scanner"],
            }
        }
    ]
    metrics = run_benchmark._compute_suite_metrics(rows)
    assert metrics["available_skills_count"] == 2

