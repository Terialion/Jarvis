import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from jarvis.benchmarks import GapClosureEngine


def test_gap_ledger_schema_and_parse() -> None:
    engine = GapClosureEngine(Path("d:/jarvis"))
    ledger = engine.load_ledger()
    entries = engine.parse_entries(ledger)
    assert ledger["version"] in ("v1", "1.0.0")
    assert len(entries) >= 1
    assert all(e.gap_level in {"none", "minor", "medium", "major", "critical"} for e in entries)


def test_score_and_gate_evaluation_consistency() -> None:
    engine = GapClosureEngine(Path("d:/jarvis"))
    entries = engine.parse_entries(engine.load_ledger())
    scores = engine.compute_scores(entries, core_e2e_pass_rate=100.0)
    gate = engine.evaluate_gate(scores, entries)
    assert gate.passed is (len(gate.blockers) == 0)
    if not gate.passed:
        assert len(gate.blockers) >= 1


def test_round_report_shape() -> None:
    engine = GapClosureEngine(Path("d:/jarvis"))
    entries = engine.parse_entries(engine.load_ledger())
    scores = engine.compute_scores(entries, core_e2e_pass_rate=88.0)
    gate = engine.evaluate_gate(scores, entries)
    top = engine.select_top_gaps(entries, limit=3)
    report = engine.build_round_report(
        round_index=1,
        goal="test",
        scope="test_scope",
        scores=scores,
        gate=gate,
        top_gaps=top,
        test_summary={"skipped": True, "results": [], "pass_rate": 0.0},
    )
    assert report["round"] == 1
    assert "required_sections" in report
    assert "Comparable Gate Status" in report["required_sections"]
    assert len(report["top_gaps"]) <= 3
