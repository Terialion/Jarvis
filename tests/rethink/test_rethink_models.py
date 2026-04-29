import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from jarvis.core.rethink.models import RETHINK_TRIGGERS, RethinkDecision


def test_rethink_models_basics():
    assert "test_failed" in RETHINK_TRIGGERS
    d = RethinkDecision(should_rethink=True, trigger="tool_failed", confidence=0.8, reason="x")
    assert d.trigger == "tool_failed"
