import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from jarvis.core.learning.skill_candidate import build_skill_candidate

def test_skill_candidate_from_experience_requires_approval():
    c = build_skill_candidate({"run_id":"r1","tool_calls":["repo_reader.search_files"]})
    assert c["requires_approval"] is True
