from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from benchmarks.case_schema import BenchmarkCase


@dataclass
class EvaluationResult:
    passed: bool
    checks: dict[str, bool] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)

    def score(self) -> float:
        if not self.checks:
            return 0.0
        ok = sum(1 for value in self.checks.values() if value)
        return ok / len(self.checks)


class BaseEvaluator:
    def evaluate(self, case: BenchmarkCase, run_result: dict[str, Any]) -> EvaluationResult:
        checks: dict[str, bool] = {
            "final_answer_exists": bool(str(run_result.get("final_answer") or "").strip() or run_result.get("status") == "partial"),
            "summary_exists": isinstance(run_result.get("summary"), dict) and bool(run_result.get("summary")),
            "stop_reason_valid": bool(str(run_result.get("stop_reason") or "").strip()),
            "event_timeline_valid": self._event_timeline_valid(run_result),
            "tool_call_schema_valid": self._tool_call_schema_valid(run_result),
        }
        checks["must_call_tools"] = self._must_call_tools(case, run_result)
        checks["no_forbidden_tool"] = self._no_forbidden_tool(case, run_result)
        checks["must_include"] = self._must_include(case, run_result)
        checks["must_not_modify_files"] = self._must_not_modify_files(case, run_result)
        checks["test_passed"] = self._test_passed(case, run_result)
        return EvaluationResult(passed=all(checks.values()), checks=checks, details={})

    @staticmethod
    def _event_timeline_valid(run_result: dict[str, Any]) -> bool:
        events = list(run_result.get("events") or [])
        return all(isinstance(evt, dict) and evt.get("event_id") and evt.get("type") for evt in events)

    @staticmethod
    def _tool_call_schema_valid(run_result: dict[str, Any]) -> bool:
        calls = list(run_result.get("tool_calls") or [])
        for call in calls:
            if not isinstance(call, dict):
                return False
            if not call.get("id") or not call.get("name"):
                return False
            if not isinstance(call.get("arguments"), dict):
                return False
        return True

    @staticmethod
    def _must_call_tools(case: BenchmarkCase, run_result: dict[str, Any]) -> bool:
        required = bool((case.expected_behavior or {}).get("must_call_tools"))
        if not required:
            return True
        return len(list(run_result.get("tool_calls") or [])) > 0

    @staticmethod
    def _no_forbidden_tool(case: BenchmarkCase, run_result: dict[str, Any]) -> bool:
        forbidden = set(case.forbidden_tools or [])
        if not forbidden:
            return True
        used = {str(call.get("name") or "") for call in list(run_result.get("tool_calls") or [])}
        return used.isdisjoint(forbidden)

    @staticmethod
    def _must_include(case: BenchmarkCase, run_result: dict[str, Any]) -> bool:
        phrase = str((case.expected_behavior or {}).get("must_include") or "").strip()
        if not phrase:
            return True
        text = str(run_result.get("final_answer") or "")
        return phrase.lower() in text.lower()

    @staticmethod
    def _must_not_modify_files(case: BenchmarkCase, run_result: dict[str, Any]) -> bool:
        no_modify = bool((case.expected_behavior or {}).get("must_not_modify_files"))
        if not no_modify:
            return True
        machine = dict((run_result.get("summary") or {}).get("machine") or {})
        return not bool(machine.get("files_changed"))

    @staticmethod
    def _test_passed(case: BenchmarkCase, run_result: dict[str, Any]) -> bool:
        requires = bool((case.expected_behavior or {}).get("test_passed"))
        if not requires:
            return True
        machine = dict((run_result.get("summary") or {}).get("machine") or {})
        tests = list(machine.get("tests_run") or [])
        return len(tests) > 0 and run_result.get("status") in {"completed", "partial"}

