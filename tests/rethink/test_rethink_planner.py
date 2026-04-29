import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from jarvis.core.rethink.planner import propose_revised_plan, propose_skill_adjustment, propose_strategy_adjustment


def test_rethink_planner_outputs():
    rp = propose_revised_plan({"trigger": "test_failed"})
    sa = propose_strategy_adjustment({"trigger": "repeated_failure"})
    ska = propose_skill_adjustment({"trigger": "policy_blocked"}, available_skills=["skill.shell_heavy"])
    assert rp.plan_actions
    assert sa.strategy in {"cautious", "explore_first", "fast_path"}
    assert "skill.shell_heavy" in ska.remove
