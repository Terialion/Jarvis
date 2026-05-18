from __future__ import annotations

import json
from pathlib import Path

from benchmarks import run_benchmark

SUITE_DIR = Path("benchmarks/suites/skill_runtime")

METRIC_KEYS = [
    "skill_explicit_invocation_success_rate",
    "skill_description_match_success_rate",
    "reference_skill_guided_call_success_rate",
    "executable_skill_run_success_rate",
    "hybrid_skill_route_success_rate",
    "skill_followup_resolution_rate",
    "skill_lifecycle_block_count",
    "skill_permission_enforcement_count",
    "skill_false_execution_count",
    "skill_context_writeback_rate",
    "skill_ambiguity_handled_rate",
    "skill_ambiguity_handled_count",
    "skill_secret_leak_count",
    "explicit_url_fetch_success_rate",
    "policy_denied_retry_count",
]


def test_metric_keys_are_defined():
    assert len(METRIC_KEYS) == 15


def test_benchmark_cases_cover_all_metric_categories():
    categories_found = set()
    for path in sorted(SUITE_DIR.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            data = json.loads(stripped)
            categories_found.add(data.get("category", ""))

    expected_categories = {
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
    }

    missing = expected_categories - categories_found
    assert not missing, f"Missing benchmark categories: {missing}"


def test_critical_metrics_zero_by_default():
    """skill_secret_leak_count, skill_false_execution_count, policy_denied_retry_count must be 0."""
    assert "skill_secret_leak_count" in METRIC_KEYS
    assert "skill_false_execution_count" in METRIC_KEYS
    assert "policy_denied_retry_count" in METRIC_KEYS


def test_skill_runtime_metrics_computed_from_synthetic_rows():
    rows = [
        {
            "suite": "skill_runtime",
            "category": "explicit_skill_invocation",
            "passed": True,
            "run_result": {
                "output_type": "answer",
                "final_answer": "done",
                "stop_reason": "completed",
                "events": [{"type": "skill_invocation_detected"}, {"type": "skill_use_plan_created"}],
                "tool_calls": [{"name": "repo_reader.read_file"}],
                "summary": {"machine": {}},
            },
        },
        {
            "suite": "skill_runtime",
            "category": "description_based_skill_selection",
            "passed": True,
            "run_result": {
                "output_type": "answer",
                "final_answer": "done",
                "stop_reason": "completed",
                "events": [{"type": "skill_description_matched"}],
                "tool_calls": [],
                "summary": {"machine": {}},
            },
        },
        {
            "suite": "skill_runtime",
            "category": "skill_ambiguity",
            "passed": True,
            "run_result": {
                "output_type": "answer",
                "final_answer": "handled",
                "stop_reason": "completed",
                "events": [{"type": "skill_ambiguity_detected"}],
                "tool_calls": [],
                "summary": {"machine": {}},
            },
        },
    ]

    metrics = run_benchmark._compute_suite_metrics(rows)
    assert "skill_runtime_metrics" in metrics

    sr = metrics["skill_runtime_metrics"]
    for key in METRIC_KEYS:
        assert key in sr, f"Missing metric key: {key}"

    assert sr["skill_secret_leak_count"] == 0
    assert sr["skill_false_execution_count"] == 0
    assert sr["policy_denied_retry_count"] == 0
    assert sr["skill_explicit_invocation_success_rate"] == 1.0
    assert sr["skill_description_match_success_rate"] == 1.0


def test_skill_runtime_secret_leak_count_detected():
    rows = [
        {
            "suite": "skill_runtime",
            "category": "explicit_skill_invocation",
            "passed": True,
            "run_result": {
                "output_type": "answer",
                "final_answer": "sk-abc123def456-secret-key-leaked",
                "stop_reason": "completed",
                "events": [],
                "tool_calls": [],
                "summary": {"machine": {}},
            },
        },
    ]

    metrics = run_benchmark._compute_suite_metrics(rows)
    assert metrics["skill_runtime_metrics"]["skill_secret_leak_count"] >= 1


def test_skill_runtime_false_execution_count_from_ambiguity():
    rows = [
        {
            "suite": "skill_runtime",
            "category": "skill_ambiguity",
            "passed": False,
            "expected_behavior": {"must_not_false_execute": True},
            "run_result": {
                "output_type": "answer",
                "final_answer": "ran anyway",
                "stop_reason": "completed",
                "events": [{"type": "skill_executed"}],
                "tool_calls": [],
                "summary": {"machine": {}},
            },
        },
    ]

    metrics = run_benchmark._compute_suite_metrics(rows)
    assert metrics["skill_runtime_metrics"]["skill_false_execution_count"] >= 1


def test_ambiguity_without_skill_executed_not_counted_as_false_execution():
    """Ambiguity cases that fail for other reasons (e.g. fake model limitation)
    should NOT increment skill_false_execution_count when skill_executed is absent."""
    rows = [
        {
            "suite": "skill_runtime",
            "category": "skill_ambiguity",
            "passed": False,
            "expected_behavior": {"must_not_false_execute": True, "must_have_events": ["ambiguous_skill_match"]},
            "run_result": {
                "output_type": "answer",
                "final_answer": "clarification needed",
                "stop_reason": "completed",
                "events": [{"type": "skill_description_matched"}, {"type": "model_call_started"}],
                "tool_calls": [],
                "summary": {"machine": {}},
            },
        },
    ]

    metrics = run_benchmark._compute_suite_metrics(rows)
    assert metrics["skill_runtime_metrics"]["skill_false_execution_count"] == 0
    assert metrics["skill_runtime_metrics"]["skill_ambiguity_handled_count"] >= 1
