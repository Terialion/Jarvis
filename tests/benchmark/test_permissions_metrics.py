from __future__ import annotations

from benchmarks import run_benchmark


def test_permissions_metrics_compute_expected_fields():
    rows = [
        {
            "suite": "permissions",
            "category": "approval_required",
            "run_result": {
                "output_type": "partial",
                "stop_reason": "approval_required",
                "final_answer": "ok",
                "events": [],
                "tool_calls": [],
                "summary": {
                    "machine": {
                        "permission_policy_evaluated": True,
                        "approval_required": True,
                        "approval_created": True,
                    }
                },
            },
        },
        {
            "suite": "permissions",
            "category": "pretool_hooks",
            "run_result": {
                "output_type": "partial",
                "stop_reason": "completed",
                "final_answer": "ok",
                "events": [],
                "tool_calls": [],
                "summary": {
                    "machine": {
                        "pretool_hook_run": True,
                        "pretool_hook_denied": True,
                        "security_warning_emitted": True,
                    }
                },
            },
        },
    ]
    metrics = run_benchmark._compute_suite_metrics(rows)["permissions_metrics"]
    assert metrics["permission_policy_evaluation_count"] >= 1
    assert metrics["approval_required_count"] >= 1
    assert metrics["pretool_hook_denied_count"] >= 1
