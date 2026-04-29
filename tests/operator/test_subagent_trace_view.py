import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from jarvis.core.subagents.models import SubagentRun
from jarvis.core.subagents.runner import SubagentRunner

def test_subagent_trace_view_data_available():
    r = SubagentRunner().run_subtask(SubagentRun(subagent_id="s", parent_run_id="p", task="x"))
    assert len(r["trace"]) >= 1
