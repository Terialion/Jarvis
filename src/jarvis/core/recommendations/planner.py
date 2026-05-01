from __future__ import annotations

from typing import Any

from .schema import RecommendedAction


def recommend_next_actions(context: dict[str, Any]) -> list[RecommendedAction]:
    stage = str(context.get("current_stage") or "")
    stop_reason = str(context.get("stop_reason") or "")
    if stage == "repo_inspection":
        return [
            RecommendedAction("Run a scoped coding smoke", "Repo inspection completed and the next useful gate is a coding smoke with a small edit/test loop."),
            RecommendedAction("Review entrypoints and tests", "Use the inspection result to choose a focused validation target."),
        ]
    if stop_reason == "done":
        return [RecommendedAction("Start Context / Resume / Compact", "Coding loop reached a clean done stop_reason.", "high")]
    if stop_reason == "max_rounds":
        return [RecommendedAction("Inspect loop evidence", "The loop exhausted rounds and needs better rethink/replan input.", "high")]
    if stop_reason == "approval_required":
        return [RecommendedAction("Approve or reject pending action", "The next write or shell step is waiting on operator approval.", "high")]
    if stop_reason in {"test_failed", "patch_failed"}:
        return [RecommendedAction("Inspect failing output", "The failure observation should guide the next replan.", "high")]
    return [RecommendedAction("Clarify next goal", "No specific next action matched the current state.")]
