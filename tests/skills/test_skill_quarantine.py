import os, sys
from jarvis.core.skill_harness.registry import SkillRegistry

def test_skill_quarantine_disabled_on_register():
    reg = SkillRegistry()
    res = reg.register_skill({"skill_id":"s2","skill_name":"S2","source":"third_party","permissions":["shell.exec_all"],"trust_level":"untrusted"})
    assert res["ok"]
    assert res["data"]["status"] == "disabled"
