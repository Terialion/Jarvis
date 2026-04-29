import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from jarvis.benchmarks.gap_closure import GapClosureEngine


def test_minor_entry_needs_evidence_for_high_score():
    engine = GapClosureEngine(Path("d:/jarvis"))
    entries = engine.parse_entries(engine.load_ledger())
    scores = engine.compute_scores(entries, core_e2e_pass_rate=100.0)
    # if score is high, evidence docs must also exist (guards against ledger-only uplift)
    if scores["functional_coverage"] >= 85:
        assert Path("d:/jarvis/docs/benchmarks/capability_evidence_matrix.md").exists()
        assert Path("d:/jarvis/docs/benchmarks/comparable_gate_evidence_audit.md").exists()
