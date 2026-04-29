import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from jarvis.core.rethink.planner import propose_skill_adjustment


def test_rethink_skill_adjustment_for_policy_blocked():
    out = propose_skill_adjustment({"trigger": "policy_blocked"}, available_skills=["skill.shell_heavy"])
    assert "skill.shell_heavy" in out.remove
