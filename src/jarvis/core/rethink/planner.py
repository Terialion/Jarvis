from __future__ import annotations

from typing import Any

from .models import RevisedPlan, SkillAdjustment, StrategyAdjustment


def propose_revised_plan(context: dict[str, Any]) -> RevisedPlan:
    trigger = str(context.get("trigger") or "none")
    actions: list[dict[str, Any]] = []
    if trigger in {"test_failed", "tool_failed", "repeated_failure"}:
        actions.append({"tool": "repo_reader.search_files", "query": "failing test OR traceback"})
        actions.append({"tool": "test_runner.run_test", "command": "pytest -q"})
    elif trigger == "low_route_confidence":
        actions.append({"tool": "repo_reader.search_files", "query": "README OR docs"})
    else:
        actions.append({"tool": "repo_reader.search_symbol", "symbol": "main"})
    return RevisedPlan(plan_actions=actions, rationale=f"rethink trigger: {trigger}")


def propose_strategy_adjustment(context: dict[str, Any]) -> StrategyAdjustment:
    trigger = str(context.get("trigger") or "none")
    if trigger in {"repeated_failure", "subagent_failed"}:
        return StrategyAdjustment(strategy="cautious", reason="failure_isolation")
    if trigger == "low_route_confidence":
        return StrategyAdjustment(strategy="explore_first", reason="confidence_recovery")
    return StrategyAdjustment(strategy="fast_path", reason="default_rethink")


def propose_skill_adjustment(context: dict[str, Any], available_skills: list[str] | None = None) -> SkillAdjustment:
    trigger = str(context.get("trigger") or "none")
    skills = list(available_skills or [])
    add: list[str] = []
    remove: list[str] = []
    if trigger in {"test_failed", "repeated_failure"} and "skill.repo_fix" in skills:
        add.append("skill.repo_fix")
    if trigger == "policy_blocked":
        remove.append("skill.shell_heavy")
    return SkillAdjustment(add=add, remove=remove, reason=f"trigger={trigger}")
