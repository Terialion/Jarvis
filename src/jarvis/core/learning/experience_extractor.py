from __future__ import annotations

from typing import Any


def extract_experience_from_run(run_result: dict[str, Any]) -> dict[str, Any]:
    traces = list(run_result.get("traces") or [])
    tool_calls = [t.get("chosen_tool") for t in traces if t.get("chosen_tool")]
    failures = [t for t in traces if not ((t.get("action_result") or {}).get("ok", True))]
    return {
        "run_id": run_result.get("run_id"),
        "tool_calls": tool_calls,
        "failure_count": len(failures),
        "step_count": len(traces),
    }

