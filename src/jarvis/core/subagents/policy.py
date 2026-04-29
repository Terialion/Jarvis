from __future__ import annotations


def validate_subtask_budget(budget_steps: int) -> dict:
    if budget_steps <= 0:
        return {"ok": False, "error": {"code": "SUBAGENT_INVALID_BUDGET", "message": "budget_steps must be > 0"}}
    if budget_steps > 50:
        return {"ok": False, "error": {"code": "SUBAGENT_INVALID_BUDGET", "message": "budget_steps too high"}}
    return {"ok": True, "data": {"budget_steps": budget_steps}}

