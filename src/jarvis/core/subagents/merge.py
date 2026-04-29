from __future__ import annotations

from typing import Any


def merge_subagent_result(parent_trace: list[dict[str, Any]], subagent_result: dict[str, Any]) -> list[dict[str, Any]]:
    merged = list(parent_trace)
    merged.append(
        {
            "step": "subagent_merge",
            "subagent_id": subagent_result.get("subagent_id"),
            "status": subagent_result.get("status"),
            "result": subagent_result.get("result"),
        }
    )
    return merged

