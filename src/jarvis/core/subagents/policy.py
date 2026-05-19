from __future__ import annotations


def validate_subtask_budget(budget_steps: int) -> dict:
    if budget_steps <= 0:
        return {"ok": False, "error": {"code": "SUBAGENT_INVALID_BUDGET", "message": "budget_steps must be > 0"}}
    if budget_steps > 50:
        return {"ok": False, "error": {"code": "SUBAGENT_INVALID_BUDGET", "message": "budget_steps too high"}}
    return {"ok": True, "data": {"budget_steps": budget_steps}}


# Stub — will be fleshed out in Task 2 (Tool restriction policy by agent_type)
def check_depth(current_depth: int, max_depth: int) -> dict:
    """Check if the current depth is within limits."""
    if current_depth > max_depth:
        return {"ok": False, "error": {"code": "MAX_DEPTH_EXCEEDED", "message": f"Depth {current_depth} exceeds max {max_depth}"}}
    return {"ok": True}


# Stub — will be fleshed out in Task 2
def tool_whitelist_for_type(agent_type: str) -> list[str]:
    """Return the tool whitelist for a given agent type."""
    return []

