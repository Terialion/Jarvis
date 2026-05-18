from __future__ import annotations

import json
from pathlib import Path


SUITE_DIR = Path("benchmarks/suites/skill_runtime")

REQUIRED_CASES = [
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


def test_all_required_benchmark_cases_exist():
    for case_name in REQUIRED_CASES:
        path = SUITE_DIR / f"{case_name}.jsonl"
        assert path.exists(), f"Missing benchmark case: {case_name}.jsonl"


def test_all_benchmark_cases_parseable_jsonl():
    for case_name in REQUIRED_CASES:
        path = SUITE_DIR / f"{case_name}.jsonl"
        if not path.exists():
            continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                data = json.loads(stripped)
                assert isinstance(data, dict), f"{case_name} line {line_no}: not a dict"
                assert "id" in data, f"{case_name} line {line_no}: missing id"
                assert "suite" in data, f"{case_name} line {line_no}: missing suite"
                assert data["suite"] == "skill_runtime", f"{case_name} line {line_no}: suite != skill_runtime"
            except json.JSONDecodeError as exc:
                raise AssertionError(f"{case_name} line {line_no}: invalid JSON: {exc}")


def test_benchmark_cases_have_expected_checks():
    for case_name in REQUIRED_CASES:
        path = SUITE_DIR / f"{case_name}.jsonl"
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            data = json.loads(stripped)
            expected = data.get("expected", {})
            assert "must_not_leak_secrets" in expected, f"{data['id']}: missing must_not_leak_secrets"
            assert "must_output_type" in expected, f"{data['id']}: missing must_output_type"
