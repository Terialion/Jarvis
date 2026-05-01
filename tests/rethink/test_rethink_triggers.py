import os
import sys


from jarvis.core.rethink.triggers import classify_rethink_trigger, should_rethink


def test_rethink_trigger_classification():
    assert classify_rethink_trigger({"test_failed": True}) == "test_failed"
    assert classify_rethink_trigger({"route_confidence": 0.2}) == "low_route_confidence"
    assert should_rethink({"tool_failed": True}) is True
