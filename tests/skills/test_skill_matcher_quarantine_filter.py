import os, sys
from jarvis.core.skill_harness.registry import SkillRegistry
from jarvis.core.skill_harness.matcher import SkillMatcher

def test_quarantined_skill_not_selected():
    reg = SkillRegistry()
    reg.register_skill({"skill_id":"q1","skill_name":"Q1","source":"third_party","permissions":["shell.exec_all"],"trust_level":"untrusted","required_tools":[],"tags":["command"]})
    reg.register_skill({"skill_id":"b1","skill_name":"B1","source":"bundled","permissions":[],"trust_level":"trusted","required_tools":[],"tags":["safe"]})
    skills = reg.filter_skills(status="enabled")["data"]["items"]
    matched = SkillMatcher().match_skills("safe task", {}, [], skills, {})
    ids = matched["data"]["selected_skills"]
    assert "q1" not in ids
