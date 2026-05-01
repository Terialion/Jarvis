from __future__ import annotations

from typing import Any


def build_final_review(result: dict[str, Any]) -> dict[str, Any]:
    changed_files = list(result.get("changed_files") or [])
    test_results = list(result.get("test_results") or [])
    last_test = test_results[-1] if test_results else {}
    return {
        "status": result.get("status", "unknown"),
        "stop_reason": result.get("stop_reason"),
        "rounds": result.get("rounds", 0),
        "changed_files": changed_files,
        "test_status": "passed" if last_test.get("passed") else ("not_run" if not last_test else "failed"),
        "risk_level": result.get("risk_level", "medium"),
        "next_suggestions": list(result.get("next_suggestions") or []),
        "evidence_refs": [result.get("trace_path")] if result.get("trace_path") else [],
    }

