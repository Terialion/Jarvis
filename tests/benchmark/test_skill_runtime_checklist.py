from __future__ import annotations

import json
from pathlib import Path

from benchmarks import export_answer_checklist

SUITE_DIR = Path("benchmarks/suites/skill_runtime")

PHASE21_DONE_CHECKS = [
    "explicit_skill_invocation",
    "description_based_skill_selection",
    "reference_only_skill_usage",
    "executable_skill_usage",
    "hybrid_skill_usage",
    "loaded_skill_followup",
    "skill_lifecycle_blocking",
    "skill_permission_enforcement",
    "skill_use_plan_events",
    "skill_context_writeback",
    "skill_ambiguity",
    "skill_usage_telemetry",
    "explicit_url_fetch_policy",
]

SKILL_RUNTIME_CHECKLIST_FIELDS = [
    "explicit_skill_invocation_ok",
    "skill_description_match_ok",
    "skill_loaded_on_demand",
    "reference_skill_guided_tool_call_ok",
    "reference_skill_not_falsely_executed",
    "executable_skill_run_ok",
    "hybrid_skill_route_ok",
    "loaded_skill_followup_ok",
    "ambiguous_skill_not_guessed",
    "disabled_skill_blocked",
    "quarantined_skill_blocked",
    "skill_use_plan_recorded",
    "skill_context_writeback_ok",
    "compact_skill_index_no_full_body",
    "explicit_url_fetch_policy_ok",
    "policy_denied_not_retried",
    "skill_runtime_secret_leak_count",
    "skill_runtime_false_execution_count",
    "skill_runtime_ambiguity_handled_count",
    "skill_runtime_policy_denied_retry_count",
]


def test_all_done_checks_have_benchmark_case():
    missing = []
    for check in PHASE21_DONE_CHECKS:
        path = SUITE_DIR / f"{check}.jsonl"
        if not path.exists():
            missing.append(check)
    assert not missing, f"Phase 21 DONE checks missing benchmark cases: {missing}"


def test_each_case_asserts_no_secret_leaks():
    for path in sorted(SUITE_DIR.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            data = json.loads(stripped)
            expected = data.get("expected", {})
            assert expected.get("must_not_leak_secrets") is True, (
                f"{data['id']}: must_not_leak_secrets must be true for all skill_runtime cases"
            )


def test_each_case_has_valid_output_type_check():
    for path in sorted(SUITE_DIR.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            data = json.loads(stripped)
            expected = data.get("expected", {})
            output_types = expected.get("must_output_type", [])
            assert len(output_types) > 0, f"{data['id']}: must_output_type is empty"


def test_checklist_export_includes_skill_runtime_fields(tmp_path: Path, monkeypatch):
    payload = {
        "generated_at": "2026-01-01T00:00:00Z",
        "scope": "skill_runtime",
        "execution_mode": "fake_model",
        "model_provider": "fake",
        "model_name": "fake-agent-v0",
        "model_backend": "fake",
        "suites": [
            {
                "suite": "skill_runtime",
                "total": 1,
                "pass_rate": 1.0,
                "metrics": {},
                "results": [
                    {
                        "case_id": "skill_runtime_invoke_001",
                        "suite": "skill_runtime",
                        "passed": True,
                        "score": 1.0,
                        "checks": {"ok": True},
                        "run_result": {
                            "output_type": "tool_result",
                            "final_answer": "done",
                            "stop_reason": "completed",
                            "tool_calls": [{"name": "repo_reader.read_file"}],
                            "events": [
                                {"type": "skill_invocation_detected"},
                                {"type": "skill_use_plan_created"},
                            ],
                            "summary": {"machine": {}},
                            "available_skills": ["summarize_file"],
                            "loaded_skills": ["summarize_file"],
                            "skill_loads_count": 1,
                            "skills_used": ["summarize_file"],
                            "skill_calls_count": 1,
                            "skill_results": [],
                        },
                    }
                ],
            }
        ],
    }

    monkeypatch.chdir(tmp_path)
    (tmp_path / "benchmarks" / "reports").mkdir(parents=True, exist_ok=True)
    (tmp_path / "benchmarks" / "suites" / "skill_runtime").mkdir(parents=True, exist_ok=True)
    (tmp_path / "benchmarks" / "reports" / "latest.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    (tmp_path / "benchmarks" / "suites" / "skill_runtime" / "explicit_skill_invocation.jsonl").write_text(
        json.dumps(
            {
                "id": "skill_runtime_invoke_001",
                "suite": "skill_runtime",
                "category": "explicit_skill_invocation",
                "input": "use summarize_file skill to summarize README.md",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert export_answer_checklist.main() == 0
    rows = json.loads(
        (tmp_path / "temp" / "benchmark_answer_checklist.json").read_text(encoding="utf-8")
    )["rows"]
    assert len(rows) == 1

    row = rows[0]
    for field in SKILL_RUNTIME_CHECKLIST_FIELDS:
        assert field in row, f"Missing checklist field: {field}"

    assert row["skill_runtime_secret_leak_count"] == 0
    assert row["skill_runtime_false_execution_count"] == 0
    assert row["skill_runtime_policy_denied_retry_count"] == 0
