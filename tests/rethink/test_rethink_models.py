import os
import sys


from jarvis.core.rethink.models import RETHINK_TRIGGERS, RethinkDecision


def test_rethink_models_basics():
    assert "test_failed" in RETHINK_TRIGGERS
    d = RethinkDecision(should_rethink=True, trigger="tool_failed", confidence=0.8, reason="x")
    assert d.trigger == "tool_failed"
