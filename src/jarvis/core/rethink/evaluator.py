from __future__ import annotations

from .models import RethinkDecision, RethinkResult
from .planner import propose_revised_plan, propose_skill_adjustment, propose_strategy_adjustment
from .triggers import classify_rethink_trigger, should_rethink


def evaluate_rethink(context: dict, available_skills: list[str] | None = None) -> RethinkResult:
    trigger = classify_rethink_trigger(context)
    decision = RethinkDecision(
        should_rethink=should_rethink(context),
        trigger=trigger,
        confidence=0.8 if trigger != "none" else 0.0,
        reason=f"trigger={trigger}",
    )
    revised = propose_revised_plan({**context, "trigger": trigger})
    strategy = propose_strategy_adjustment({**context, "trigger": trigger})
    skill = propose_skill_adjustment({**context, "trigger": trigger}, available_skills=available_skills)
    return RethinkResult(
        decision=decision,
        revised_plan=revised,
        strategy_adjustment=strategy,
        skill_adjustment=skill,
    )
