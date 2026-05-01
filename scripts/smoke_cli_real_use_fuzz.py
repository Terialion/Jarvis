"""
Smoke test runner for Jarvis CLI using natural language test cases.

Runs real `python -m jarvis.cli` with batch stdin input,
checks output against expected behavior, and records failures.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Adjust this import to match your project layout
try:
    from natural_language_test_cases import (
        NaturalLanguageTestCase,
        get_all_test_cases,
    )
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from natural_language_test_cases import (
        NaturalLanguageTestCase,
        get_all_test_cases,
    )

try:
    from cli_smoke_lib import CliRunResult, run_cli_session
except ImportError:
    from scripts.cli_smoke_lib import CliRunResult, run_cli_session


# Where to write findings
_FINDINGS_PATH = Path(__file__).resolve().parents[1] / "temp" / "cli_harness_findings.jsonl"


def _stdout_has_phrase(stdout: str, phrase: str) -> bool:
    return phrase.lower() in stdout.lower()


def _stdout_has_any_forbidden(stdout: str, forbidden: List[str]) -> List[str]:
    found = []
    for phrase in forbidden:
        if _stdout_has_phrase(stdout, phrase):
            found.append(phrase)
    return found


def _check_must_not_clarify(stdout: str) -> bool:
    """
    Return True if output contains a clarification question
    that should NOT be present.
    """
    clarify_markers = [
        "我需要再确认一下",
        "你是想让我创建/修改代码文件，还是只写一段普通说明文本",
        "需要我帮你做什么呢",
        "请告诉我更具体的信息",
        "不太确定你想要",
    ]
    for marker in clarify_markers:
        if marker in stdout:
            return True
    return False


def _check_must_not_fake_success(stdout: str) -> bool:
    """Check if output fakes success when it shouldn't."""
    fake_markers = [
        "Completed",
        "完成",
        "成功",
        "已修复",
        "已修改",
    ]
    # This is a heuristic; override with case-specific logic
    for marker in fake_markers:
        if marker in stdout and "未" not in stdout and "没有" not in stdout:
            return True
    return False


def evaluate_test_case(
    case: NaturalLanguageTestCase,
    run_result: CliRunResult,
) -> Dict[str, Any]:
    """
    Evaluate a single test case against CLI output.
    Returns a dict with 'passed', 'failure_type', 'reason', etc.
    """
    stdout = run_result.stdout or ""
    stderr = run_result.stderr or ""
    timed_out = run_result.timed_out

    result = {
        "input": case.input,
        "category": case.category,
        "expected_response_mode": case.expected_response_mode,
        "passed": True,
        "failure_type": None,
        "reason": None,
        "stdout_excerpt": stdout[-500:] if stdout else "",
        "stderr_excerpt": stderr[-500:] if stderr else "",
        "timed_out": timed_out,
    }

    if timed_out:
        result["passed"] = False
        result["failure_type"] = "timeout"
        result["reason"] = "CLI timed out"
        return result

    if run_result.error:
        result["passed"] = False
        result["failure_type"] = "execution_error"
        result["reason"] = run_result.error
        return result

    # Check: must not clarify
    if case.must_not_clarify and _check_must_not_clarify(stdout):
        result["passed"] = False
        result["failure_type"] = "bad_clarify"
        result["reason"] = "Should NOT clarify, but clarification question detected in output"
        return result

    # Check: must not enter task flow (heuristic)
    if case.must_not_enter_task_flow:
        task_markers = ["Task task_", "Plan", "Result", "Completed in safe mode"]
        for marker in task_markers:
            if marker in stdout:
                result["passed"] = False
                result["failure_type"] = "task_fallback"
                result["reason"] = f"Should not enter task flow, but '{marker}' detected"
                return result

    # Check: must not fake success
    if case.must_not_fake_success and _check_must_not_fake_success(stdout):
        result["passed"] = False
        result["failure_type"] = "fake_success"
        result["reason"] = "Should not fake success, but success-like message detected"
        return result

    # Check: forbidden phrases
    if case.forbidden_phrases:
        found = _stdout_has_any_forbidden(stdout, case.forbidden_phrases)
        if found:
            result["passed"] = False
            result["failure_type"] = "forbidden_phrase"
            result["reason"] = f"Forbidden phrase(s) found: {found}"
            return result

    # Check: expected output markers (heuristic pass)
    if case.expected_output_markers:
        has_any = any(
            _stdout_has_phrase(stdout, m) for m in case.expected_output_markers
        )
        if not has_any:
            # Don't fail immediately; this is a soft check
            result["reason"] = "Soft check: no expected output markers found"
            # result["passed"] = False
            # result["failure_type"] = "missing_expected_marker"
            return result

    return result


def run_single_case(case: NaturalLanguageTestCase, jarvis_root: str) -> Dict[str, Any]:
    """Run one test case through the real CLI and evaluate."""
    run_result = run_cli_session(
        inputs=[case.input],
        jarvis_root=jarvis_root,
        timeout=30.0,
    )
    evaluation = evaluate_test_case(case, run_result)
    evaluation["stdout_full"] = run_result.stdout or ""
    evaluation["stderr_full"] = run_result.stderr or ""
    evaluation["returncode"] = run_result.returncode
    return evaluation


def run_all_cases(
    jarvis_root: str,
    cases: Optional[List[NaturalLanguageTestCase]] = None,
    max_cases: int = 50,
) -> List[Dict[str, Any]]:
    """
    Run test cases against real CLI.
    To avoid spawning too many subprocesses, you can batch inputs.
    This initial version runs each case in its own CLI session.
    """
    if cases is None:
        cases = get_all_test_cases()
    if max_cases and len(cases) > max_cases:
        cases = cases[:max_cases]

    findings = []
    for i, case in enumerate(cases):
        print(f"[{i+1}/{len(cases)}] Testing: {case.input[:60]}")
        evaluation = run_single_case(case, jarvis_root)
        if not evaluation["passed"]:
            print(f"  FAIL: {evaluation['failure_type']} - {evaluation['reason']}")
        else:
            print(f"  PASS")
        findings.append(evaluation)

    return findings


def write_findings(findings: List[Dict[str, Any]], path: Path = _FINDINGS_PATH) -> None:
    """Write findings to a JSONL file for later analysis."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for entry in findings:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"\nFindings written to: {path}")


def summarize_findings(findings: List[Dict[str, Any]]) -> None:
    """Print a summary of findings."""
    total = len(findings)
    passed = sum(1 for f in findings if f["passed"])
    failed = total - passed

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print()

    if failed > 0:
        print("FAILURES BY TYPE:")
        by_type: Dict[str, int] = {}
        for f in findings:
            if not f["passed"]:
                ft = f.get("failure_type", "unknown")
                by_type[ft] = by_type.get(ft, 0) + 1
        for ft, count in sorted(by_type.items()):
            print(f"  {ft}: {count}")
        print()

        print("FAILED TEST CASES:")
        for f in findings:
            if not f["passed"]:
                print(f"  - [{f['category']}] {f['input'][:60]}")
                print(f"    Failure: {f['failure_type']} - {f['reason']}")
        print()

    print("=" * 60)


def main():
    jarvis_root = str(Path(__file__).resolve().parents[1])
    print(f"Jarvis root: {jarvis_root}")
    print(f"Test cases: {len(get_all_test_cases())}")
    print()

    # Run a small subset first for quick feedback
    cases = get_all_test_cases()
    # Start with the most important cases: chat, help, skill, workspace status
    priority_categories = [
        "chat", "help", "identity", "usage",
        "skill_management", "workspace_status", "project_structure",
    ]
    priority_cases = [c for c in cases if c.category in priority_categories]
    other_cases = [c for c in cases if c.category not in priority_categories]

    # Run priority cases first
    print("Running PRIORITY cases...")
    findings = run_all_cases(jarvis_root, priority_cases, max_cases=50)

    # Then run other cases
    print("\nRunning OTHER cases...")
    other_findings = run_all_cases(jarvis_root, other_cases, max_cases=50)
    findings.extend(other_findings)

    write_findings(findings)
    summarize_findings(findings)


if __name__ == "__main__":
    main()
