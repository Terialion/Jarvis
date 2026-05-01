import os, sys
from jarvis.core.skill_harness.trust import evaluate_skill_trust
from jarvis.core.skill_harness.audit import build_skill_audit_record

def test_skill_trust_and_audit():
    t = evaluate_skill_trust({"permissions":["shell.exec_all"],"trust_level":"untrusted"})
    a = build_skill_audit_record(skill_id="s1", action="register")
    assert t["data"]["quarantined"] is True
    assert a["skill_id"] == "s1"
