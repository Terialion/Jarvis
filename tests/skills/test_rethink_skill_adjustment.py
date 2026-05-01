import os
import sys


from jarvis.core.rethink.planner import propose_skill_adjustment


def test_rethink_skill_adjustment_for_policy_blocked():
    out = propose_skill_adjustment({"trigger": "policy_blocked"}, available_skills=["skill.shell_heavy"])
    assert "skill.shell_heavy" in out.remove
