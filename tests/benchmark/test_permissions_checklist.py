from __future__ import annotations

from benchmarks import run_benchmark
from benchmarks import export_answer_checklist


def test_permissions_checklist_fields_present():
    suite = run_benchmark.run_suite("permissions", model_mode="fake")
    payload = {
        "generated_at": "2026-01-01T00:00:00+00:00",
        "scope": "permissions",
        "execution_mode": "fake_model",
        "model_provider": "fake",
        "model_name": "fake-agent-v0",
        "model_backend": "fake",
        "suites": [suite],
    }
    rows = export_answer_checklist._extract_rows(payload, {})
    assert rows
    sample = rows[0]
    assert "permission_policy_evaluated" in sample
    assert "approval_required" in sample
    assert "permissions_secret_leak_count" in sample
