import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from jarvis.core.skill_harness.manifest import validate_skill_manifest

def test_skill_manifest_validation():
    ok = validate_skill_manifest({"skill_id":"s","skill_name":"S","source":"x","permissions":[],"trust_level":"trusted"})
    assert ok["ok"]
