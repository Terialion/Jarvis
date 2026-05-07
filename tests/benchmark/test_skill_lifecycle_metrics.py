from __future__ import annotations

from benchmarks import run_benchmark


def test_skill_lifecycle_metrics_compute_expected_fields():
    rows = [
        {
            "suite": "skill_lifecycle",
            "category": "install",
            "run_result": {
                "output_type": "answer",
                "stop_reason": "completed",
                "final_answer": "ok",
                "events": [],
                "tool_calls": [],
                "summary": {
                    "machine": {
                        "skill_installed": True,
                        "skill_install_validated": True,
                        "invalid_skill_not_enabled": True,
                    }
                },
            },
        },
        {
            "suite": "skill_lifecycle",
            "category": "trust_quarantine",
            "run_result": {
                "output_type": "answer",
                "stop_reason": "completed",
                "final_answer": "ok",
                "events": [],
                "tool_calls": [],
                "summary": {
                    "machine": {
                        "skill_quarantined": True,
                        "quarantined_load_blocked": True,
                        "trust_not_bypass_validator": True,
                    }
                },
            },
        },
    ]
    metrics = run_benchmark._compute_suite_metrics(rows)["skill_lifecycle_metrics"]
    assert "skill_install_success_rate" in metrics
    assert "skill_quarantine_success_rate" in metrics
    assert metrics["skill_trust_count"] >= 1
