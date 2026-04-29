import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from jarvis.core.eval.harness_metrics_store import HarnessMetricsStore

def test_operator_memory_related_summary_uses_metrics_store(tmp_path):
    s = HarnessMetricsStore(str(tmp_path / "m.jsonl"))
    s.append_event({"kind":"recovery","run_id":"r1"})
    sm = s.summarize(run_id="r1")
    assert sm["kind_distribution"]["recovery"] == 1
