import os
import sys


from jarvis.core.skill_harness.registry import SkillRegistry


def test_quarantine_reason_visible_in_registry_audit():
    reg = SkillRegistry()
    reg.register_skill({"skill_id": "third.bad", "skill_name": "bad", "source": "third_party"})
    snap = reg.snapshot()
    assert snap["ok"]
    data = snap["data"]
    assert any(i["skill_id"] == "third.bad" for i in data["items"])
    item = next(i for i in data["items"] if i["skill_id"] == "third.bad")
    assert item["status"] == "disabled"
    assert item["metadata"]["trust"]["quarantined"] is True
