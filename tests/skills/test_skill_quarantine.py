import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from jarvis.core.skill_harness.registry import SkillRegistry

def test_skill_quarantine_disabled_on_register():
    reg = SkillRegistry()
    res = reg.register_skill({"skill_id":"s2","skill_name":"S2","source":"third_party","permissions":["shell.exec_all"],"trust_level":"untrusted"})
    assert res["ok"]
    assert res["data"]["status"] == "disabled"
