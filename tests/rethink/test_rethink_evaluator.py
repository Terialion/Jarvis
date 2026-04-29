import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from jarvis.core.rethink.evaluator import evaluate_rethink


def test_rethink_evaluator_returns_adjustments():
    out = evaluate_rethink({"tool_failed": True}, available_skills=["skill.repo_fix"])
    assert out.decision.should_rethink is True
    assert out.strategy_adjustment.strategy
